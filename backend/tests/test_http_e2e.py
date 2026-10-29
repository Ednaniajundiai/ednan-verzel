"""Porte de `http.e2e.test.ts`: API + tempo real de ponta a ponta, rotas do leiloeiro por papel,
catálogo, criação, cancelamento e painel (002 e 003)."""

import asyncio
import json
import re
import secrets
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest_asyncio

from leilao.services.context import AppContext
from leilao.services.thesportsdb import TheSportsDbClient
from tests.helpers import (
    OFFLINE_SOURCE,
    Api,
    connect_socket,
    gather,
    in_ms,
    make_item,
    make_lot,
    mock_source,
    next_event,
    png_bytes,
    running_server,
    sleep,
)


@pytest_asyncio.fixture(scope='module')
async def api(ctx: AppContext) -> AsyncIterator[Api]:
    async with running_server(ctx, 'test-jwt') as base:
        client = Api(base)
        yield client
        await client.close()


async def signup(api: Api, name: str) -> str:
    _, body = await api(
        'POST',
        '/auth/register',
        {'username': f'{name[:12]}-{secrets.token_hex(5)}', 'password': 'senha-forte-123', 'role': 'bidder'},
    )
    await api('POST', '/wallet/deposit', {'amount_cents': 100_000}, token=body['token'])
    return str(body['token'])


async def register(api: Api, prefix: str, name: str, role: str) -> dict[str, Any]:
    _, body = await api(
        'POST',
        '/auth/register',
        {
            'username': f'{prefix[:12]}-{secrets.token_hex(5)}',
            'password': 'senha-forte-123',
            'role': role,
        },
    )
    return body  # type: ignore[no-any-return]


async def test_fluxo_completo_assiste_da_lance_recebe_evento_e_e_avisado_ao_ser_superado(
    ctx: AppContext, api: Api
) -> None:
    lot_id = await make_lot(ctx, starting_price_cents=1_000, min_increment_cents=100)

    alice, bob = await gather(signup(api, 'alice'), signup(api, 'bob'))
    viewer = await connect_socket(api.base)
    alice_socket = await connect_socket(api.base, alice)
    await viewer.emit('lot:join', lot_id)
    await sleep(30)

    status, alice_bid = await api(
        'POST', f'/lots/{lot_id}/bids', {'amount_cents': 1_000}, {'idempotency-key': 'a1'}, token=alice
    )
    assert status == 201
    assert alice_bid['wallet'] == {'balance_cents': 100_000, 'committed_cents': 1_000, 'available_cents': 99_000}

    placed = next_event(viewer, 'bid:placed')
    outbid = next_event(alice_socket, 'bid:outbid')
    started = time.monotonic()
    status, _ = await api('POST', f'/lots/{lot_id}/bids', {'amount_cents': 1_100}, token=bob)
    assert status == 201

    event = await asyncio.wait_for(placed, 5)
    assert time.monotonic() - started < 1  # CS7
    assert (event['lot_id'], event['amount_cents'], event['bid_count']) == (lot_id, 1_100, 2)
    assert re.fullmatch(r'[0-9a-f]{16}', event['bidder'])
    assert not re.search(r'alice|bob|@e2e', json.dumps(event))
    assert await asyncio.wait_for(outbid, 5) == {'lot_id': lot_id, 'amount_cents': 1_100}

    # Reenvio com a mesma chave: 200, mesmo lance.
    status, replay = await api(
        'POST', f'/lots/{lot_id}/bids', {'amount_cents': 1_000}, {'idempotency-key': 'a1'}, token=alice
    )
    assert status == 200
    assert replay['bid']['bidId'] == alice_bid['bid']['bidId']

    status, low = await api('POST', f'/lots/{lot_id}/bids', {'amount_cents': 1_150}, token=alice)
    assert status == 422
    assert (low['error']['code'], low['error']['minimum_cents']) == ('BID_TOO_LOW', 1_200)

    _, lot = await api('GET', f'/lots/{lot_id}', token=bob)
    assert (lot['lot']['current_price_cents'], lot['lot']['you_are_leading'], lot['lot']['next_minimum_cents']) == (
        1_100,
        True,
        1_200,
    )
    assert lot['server_now']

    _, verify = await api('GET', f'/audit/lots/{lot_id}/verify')
    assert (verify['valid'], verify['entries'], verify['head_matches_lot']) == (True, 3, True)

    await viewer.disconnect()
    await alice_socket.disconnect()


async def test_valida_entrada_e_autenticacao(api: Api) -> None:
    assert (await api('POST', '/auth/register', {'username': 'x', 'password': '1'}))[0] == 400
    assert (await api('GET', '/me'))[0] == 401
    assert (await api('GET', '/lots/nao-e-uuid'))[0] == 400
    token = await signup(api, 'carol')
    status, _ = await api('POST', '/wallet/deposit', {'amount_cents': 10.5}, token=token)
    assert status == 400  # Const. 1.1: centavos inteiros


async def test_licitante_recebe_403_ao_criar_ou_cancelar_lote_sem_token_401(ctx: AppContext, api: Api) -> None:
    lot_id = await make_lot(ctx)
    bidder = await signup(api, 'dave')
    for method, path in (('POST', '/auctioneer/lots'), ('POST', f'/auctioneer/lots/{lot_id}/cancel')):
        status, body = await api(method, path, {}, token=bidder)
        assert status == 403
        assert body['error']['code'] == 'FORBIDDEN'
        assert (await api(method, path, {}))[0] == 401


async def test_busca_de_time_camisas_do_time_e_camisas_salvas_respondem_com_a_forma_do_plan(
    ctx: AppContext, api: Api
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/searchteams.php'):
            return httpx.Response(
                200,
                json={
                    'teams': [
                        {'idTeam': '77', 'strTeam': 'Santos', 'strLeague': 'Brazilian Serie A', 'strSport': 'Soccer'}
                    ]
                },
            )
        if request.url.path.endswith('/lookupequipment.php'):
            return httpx.Response(
                200,
                json={
                    'equipment': [
                        {
                            'idEquipment': '9001',
                            'idTeam': '77',
                            'strSeason': '2012',
                            'strType': '1st',
                            'strEquipment': 'https://img.test/santos.png',
                        }
                    ]
                },
            )
        return httpx.Response(200, content=png_bytes(), headers={'content-type': 'image/png'})

    original = ctx.catalog.client
    ctx.catalog.client = mock_source(handler)
    try:
        auth = {'authorization': f'Bearer {(await register(api, "leiloeiro", "Leiloeira", "auctioneer"))["token"]}'}
        status, teams = await api('GET', '/auctioneer/catalog/teams?q=Santos', headers=auth)
        assert status == 200
        assert (teams['source'], teams['selected_team_id']) == ('live', '77')
        assert (teams['teams'][0]['id'], teams['teams'][0]['name']) == ('77', 'Santos')
        j = teams['jerseys'][0]
        assert (j['season'], j['kind_label'], j['image_status']) == ('2012', 'Titular', 'saved')

        status, jerseys = await api('GET', '/auctioneer/catalog/teams/77/jerseys', headers=auth)
        assert status == 200
        assert (jerseys['source'], jerseys['team']['id'], jerseys['jerseys'][0]['team_name']) == (
            'cache',
            '77',
            'Santos',
        )

        _, saved = await api('GET', '/auctioneer/catalog/jerseys', headers=auth)
        assert any(x['team_name'] == 'Santos' for x in saved['jerseys'])

        assert (await api('GET', '/auctioneer/catalog/teams?q=%20%20', headers=auth))[0] == 400
    finally:
        ctx.catalog.client = original


async def test_com_a_fonte_fora_do_ar_a_busca_responde_200_com_aviso_licitante_403(ctx: AppContext, api: Api) -> None:
    ctx.catalog.client = TheSportsDbClient(OFFLINE_SOURCE, timeout_ms=500)
    auth = {'authorization': f'Bearer {(await register(api, "leiloeiro", "Leiloeira", "auctioneer"))["token"]}'}
    status, body = await api('GET', '/auctioneer/catalog/teams?q=Botafogo', headers=auth)
    assert status == 200
    assert (body['source'], body['notice'], body['teams']) == ('cache', {'code': 'UPSTREAM_UNAVAILABLE'}, [])

    bidder = {'authorization': f'Bearer {await signup(api, "erin")}'}
    assert (await api('GET', '/auctioneer/catalog/teams?q=Botafogo', headers=bidder))[0] == 403
    assert (await api('GET', '/auctioneer/catalog/jerseys', headers=bidder))[0] == 403


async def test_post_auctioneer_lots_201_valido_400_com_issues_por_campo(ctx: AppContext, api: Api) -> None:
    reg = await register(api, 'criadora', 'Criadora', 'auctioneer')
    auth = {'authorization': f'Bearer {reg["token"]}'}
    item_id = await make_item(ctx)
    valid = {
        'item_id': item_id,
        'title': 'Camisa Santos 2012 titular',
        'size': 'M',
        'condition': 'nova',
        'ends_at': in_ms(3_600_000),
        'starting_price_cents': 10_000,
        'min_increment_cents': 500,
    }
    status, created = await api('POST', '/auctioneer/lots', valid, auth)
    assert status == 201
    assert uuid.UUID(created['id'])

    status, invalid = await api(
        'POST', '/auctioneer/lots', {**valid, 'title': '', 'size': 'XXL', 'starting_price_cents': 0}, auth
    )
    assert status == 400
    assert invalid['error']['code'] == 'VALIDATION'
    assert sorted(invalid['error']['issues']) == ['size', 'starting_price_cents', 'title']


async def test_cancel_200_para_o_dono_e_o_socket_recebe_lot_cancelled_409_com_lances(ctx: AppContext, api: Api) -> None:
    reg = await register(api, 'cancela', 'Dona', 'auctioneer')
    auth = {'authorization': f'Bearer {reg["token"]}'}
    lot_id = await make_lot(ctx, auctioneer_id=reg['user']['id'])
    busy = await make_lot(ctx, auctioneer_id=reg['user']['id'])
    bidder = await signup(api, 'frank')
    await api('POST', f'/lots/{busy}/bids', {'amount_cents': 100}, token=bidder)

    viewer = await connect_socket(api.base)
    await viewer.emit('lot:join', lot_id)
    await sleep(50)
    cancelled = next_event(viewer, 'lot:cancelled')

    status, ok = await api('POST', f'/auctioneer/lots/{lot_id}/cancel', None, auth)
    assert status == 200
    assert (ok['id'], ok['status']) == (lot_id, 'cancelled')
    assert await asyncio.wait_for(cancelled, 5) == {'lot_id': lot_id}

    status, refused = await api('POST', f'/auctioneer/lots/{busy}/cancel', None, auth)
    assert status == 409
    assert refused['error'] == {'code': 'LOT_HAS_BIDS', 'message': 'O lote já recebeu lances'}
    await viewer.disconnect()


async def test_get_auctioneer_lots_com_resultado_e_total_licitante_403(ctx: AppContext, api: Api) -> None:
    reg = await register(api, 'painel', 'Painel', 'auctioneer')
    lot_id = await make_lot(ctx, auctioneer_id=reg['user']['id'])
    status, panel = await api('GET', '/auctioneer/lots', token=reg['token'])
    assert status == 200
    assert panel['total_received_cents'] == 0
    (lot,) = panel['lots']
    assert (lot['id'], lot['outcome'], lot['can_cancel']) == (lot_id, 'open', True)
    assert 'auctioneer_id' not in json.dumps(panel)

    bidder = await signup(api, 'gina')
    assert (await api('GET', '/auctioneer/lots', token=bidder))[0] == 403
