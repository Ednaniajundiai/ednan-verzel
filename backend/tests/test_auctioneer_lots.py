"""Porte de `auctioneer-lots.test.ts`: criação de lote a partir de uma camisa (FR-010 a FR-014 da 002)."""

import json
import re
from collections.abc import AsyncIterator, Awaitable
from typing import Any

import httpx
import pytest
import pytest_asyncio

from leilao.lib.errors import AppError
from leilao.services.auction import create_lot, get_lot
from leilao.services.audit import list_audit_entries
from leilao.services.catalog import list_jerseys
from leilao.services.context import AppContext
from leilao.services.thesportsdb import TheSportsDbClient
from tests.helpers import (
    OFFLINE_SOURCE,
    Api,
    db_now,
    lot_input,
    lot_row,
    make_auctioneer,
    make_item,
    make_user,
    mock_source,
    outcome,
    png_bytes,
    reset_db,
    running_server,
)


@pytest_asyncio.fixture(scope='module')
async def api(ctx: AppContext) -> AsyncIterator[Api]:
    async with running_server(ctx, 'jwt') as base:
        client = Api(base)
        yield client
        await client.close()


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    ctx.catalog.client = TheSportsDbClient(OFFLINE_SOURCE, timeout_ms=300)
    yield


async def catalog_jersey(ctx: AppContext) -> str:
    """Camisa ligada a um time do catálogo, como sai da busca (com liga e time)."""
    await ctx.db.query(
        "INSERT INTO catalog_teams (external_id, name, league, country) VALUES ('134296', 'Flamengo', 'Brazilian Serie A', 'Brazil')"
    )
    res = await ctx.db.query(
        """INSERT INTO items (external_id, source, title, image_path, image_source_url, team_external_id, season, kind)
     VALUES ('tsdb-equipment:4710', 'thesportsdb', 'Camisa Flamengo 2019-2020 titular', 'fla.png',
             'https://img.test/fla.png', '134296', '2019-2020', '1st') RETURNING id"""
    )
    return str(res.rows[0]['id'])


async def issues_of(aw: Awaitable[Any]) -> dict[str, list[str]]:
    with pytest.raises(AppError) as err:
        await aw
    assert err.value.code == 'VALIDATION'
    return (err.value.details or {}).get('issues', {})


FLAMENGO_ATTRS = {'team': 'Flamengo', 'league': 'Brazilian Serie A', 'season': '2019-2020', 'kind': '1st'}


async def test_fr011_pertence_ao_leiloeiro_e_copia_titulo_tamanho_estado_atributos_e_imagem(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    item_id = await catalog_jersey(ctx)
    created = await create_lot(
        ctx,
        owner['id'],
        lot_input(item_id, title='  Camisa Flamengo 2019 titular autografada ', size='G', condition='usada'),
    )
    lot = await lot_row(ctx, created['id'])
    assert lot['auctioneer_id'] == owner['id']
    assert lot['title'] == 'Camisa Flamengo 2019 titular autografada'
    assert (lot['size'], lot['condition'], lot['image_path'], lot['status']) == ('G', 'usada', 'fla.png', 'open')
    assert lot['attributes'] == FLAMENGO_ATTRS


async def test_lot_opened_sem_o_dono_e_leituras_publicas_sem_dono_nem_papel(ctx: AppContext, api: Api) -> None:
    owner = await make_auctioneer(ctx)
    created = await create_lot(
        ctx, owner['id'], lot_input(await catalog_jersey(ctx), size='P', condition='nova_com_etiqueta')
    )
    lot_id = created['id']

    opened = (await list_audit_entries(ctx.db, lot_id))[0]
    payload = json.loads(opened['payload_canonical'])
    assert opened['event_type'] == 'lot_opened'
    assert payload['title'] == 'Camisa de teste'
    assert (payload['size'], payload['condition']) == ('P', 'nova_com_etiqueta')
    assert payload['attributes'] == FLAMENGO_ATTRS

    lot_res = (await api.get(f'/lots/{lot_id}')).text
    audit_res = (await api.get(f'/audit/lots/{lot_id}')).text
    for body in (opened['payload_canonical'], lot_res, audit_res):
        assert owner['id'] not in body
        assert owner['username'] not in body
        assert not re.search('auctioneer', body)
    item = json.loads(lot_res)['lot']['item']
    assert (item['title'], item['size'], item['image_url']) == ('Camisa de teste', 'P', '/images/fla.png')


async def test_licitante_nao_cria_lote_checagem_tambem_no_servico(ctx: AppContext) -> None:
    bidder = await make_user(ctx)
    assert await outcome(create_lot(ctx, bidder['id'], lot_input(await make_item(ctx)))) == 'FORBIDDEN'


async def test_fr012_recusa_titulo_vazio_valores_zerados_e_opcoes_inexistentes(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    item_id = await make_item(ctx)
    issues = await issues_of(
        create_lot(
            ctx,
            owner['id'],
            {
                **lot_input(item_id),
                'title': '   ',
                'starting_price_cents': 0,
                'min_increment_cents': 0,
                'size': 'XXL',
                'condition': 'rasgada',
            },
        )
    )
    assert sorted(issues) == ['condition', 'min_increment_cents', 'size', 'starting_price_cents', 'title']
    assert (await ctx.db.query('SELECT 1 FROM lots')).rowcount == 0


async def test_fr012_fim_igual_ou_anterior_ao_inicio_e_recusado_no_campo_ends_at(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    item_id = await make_item(ctx)
    starts_at = await db_now(ctx, 10 * 60_000)
    for ends_at in (starts_at, await db_now(ctx, 5 * 60_000)):
        issues = await issues_of(create_lot(ctx, owner['id'], lot_input(item_id, starts_at=starts_at, ends_at=ends_at)))
        assert list(issues) == ['ends_at']


async def test_fr012_inicio_no_passado_tolerancia_de_1_min(ctx: AppContext) -> None:
    """−2 min é recusado, −30 s é aceito (relógio do banco)."""
    owner = await make_auctioneer(ctx)
    item_id = await make_item(ctx)
    late = await issues_of(create_lot(ctx, owner['id'], lot_input(item_id, starts_at=await db_now(ctx, -2 * 60_000))))
    assert list(late) == ['starts_at']
    created = await create_lot(ctx, owner['id'], lot_input(item_id, starts_at=await db_now(ctx, -30_000)))
    assert created['id']


async def test_fr012_inicio_omitido_vale_como_agora(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    created = await create_lot(ctx, owner['id'], lot_input(await make_item(ctx)))
    res = await ctx.db.query(
        'SELECT starts_at <= clock_timestamp() AS started FROM lots WHERE id = $1', [created['id']]
    )
    assert res.rows[0]['started'] is True


def source_with_image(ok: bool) -> TheSportsDbClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        if ok:
            return httpx.Response(200, content=png_bytes(), headers={'content-type': 'image/png'})
        return httpx.Response(503, content=b'x')

    return mock_source(handler)


async def test_fr013_imagem_pendente_que_nao_baixa_image_unavailable(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    item_id = await make_item(ctx, image='pending')
    ctx.catalog.client = source_with_image(False)
    assert await outcome(create_lot(ctx, owner['id'], lot_input(item_id))) == 'IMAGE_UNAVAILABLE'
    assert (await ctx.db.query('SELECT 1 FROM lots')).rowcount == 0


async def test_fr013_imagem_pendente_que_baixa_agora_lote_criado_com_a_imagem(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    item_id = await make_item(ctx, image='pending')
    ctx.catalog.client = source_with_image(True)
    created = await create_lot(ctx, owner['id'], lot_input(item_id))
    assert re.fullmatch(r'[0-9a-f]{64}\.png', (await lot_row(ctx, created['id']))['image_path'])


async def test_fr013_camisa_sem_imagem_na_fonte_e_recusada(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    item_id = await make_item(ctx, image='none')
    assert await outcome(create_lot(ctx, owner['id'], lot_input(item_id))) == 'ITEM_WITHOUT_IMAGE'


async def test_fr010_mesma_camisa_dois_lotes_que_nao_mudam_com_o_catalogo(ctx: AppContext) -> None:
    """Os lotes não mudam quando o catálogo muda e a fonte cai."""
    owner = await make_auctioneer(ctx)
    item_id = await catalog_jersey(ctx)
    a = await create_lot(ctx, owner['id'], lot_input(item_id, title='Lote A'))
    b = await create_lot(ctx, owner['id'], lot_input(item_id, title='Lote B'))
    assert a['id'] != b['id']

    # Nova consulta à fonte muda título, temporada e imagem da camisa no catálogo.
    def handler(request: httpx.Request) -> httpx.Response:
        if 'lookupequipment' in str(request.url):
            return httpx.Response(
                200,
                json={
                    'equipment': [
                        {
                            'idEquipment': '4710',
                            'idTeam': '134296',
                            'strSeason': '2020-2021',
                            'strType': '2nd',
                            'strEquipment': 'https://img.test/nova.png',
                        }
                    ]
                },
            )
        return httpx.Response(200, content=png_bytes(), headers={'content-type': 'image/png'})

    ctx.catalog.client = mock_source(handler)
    await list_jerseys(ctx, '134296')
    row = (await ctx.db.query('SELECT title, season, image_path FROM items WHERE id = $1', [item_id])).rows[0]
    assert (row['title'], row['season']) == ('Camisa Flamengo 2020-2021 reserva', '2020-2021')
    assert row['image_path'] != 'fla.png'

    ctx.catalog.client = TheSportsDbClient(OFFLINE_SOURCE, timeout_ms=300)
    for lot_id, title in ((a['id'], 'Lote A'), (b['id'], 'Lote B')):
        item = (await get_lot(ctx, lot_id))['item']
        assert (item['title'], item['image_url'], item['attributes']) == (title, '/images/fla.png', FLAMENGO_ATTRS)
