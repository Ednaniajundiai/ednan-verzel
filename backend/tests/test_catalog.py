"""Porte de `catalog.test.ts`: catálogo local primeiro, falhas da fonte e disjuntor (FR-006 a FR-009 da 002)."""

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from leilao.services.catalog import list_jerseys, list_saved_jerseys, search_teams
from leilao.services.context import AppContext
from tests.helpers import FIXTURES, mock_source, outcome, reset_db

SOURCE = FIXTURES / 'thesportsdb'
FLAMENGO = '134296'
PALMEIRAS = '134465'

Handler = Callable[[httpx.Request], httpx.Response]


def fixture(name: str) -> bytes:
    return (SOURCE / name).read_bytes()


def json_response(body: bytes | str, status: int = 200, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, content=body, headers={'content-type': 'application/json', **(headers or {})})


def healthy(request: httpx.Request) -> httpx.Response:
    """Fonte saudável, no formato da TheSportsDB (respostas gravadas)."""
    path = request.url.path
    if path.endswith('/searchteams.php'):
        term = (request.url.params.get('t') or '').lower()
        if term == 'palmeiras':
            return json_response(fixture('searchteams-palmeiras.json'))
        if term.startswith('fla'):
            return json_response(fixture('searchteams-flamengo.json'))
        return json_response('{"teams":null}')
    if path.endswith('/lookupequipment.php'):
        team = request.url.params.get('id')
        if team == FLAMENGO:
            return json_response(fixture('lookupequipment-flamengo.json'))
        if team == PALMEIRAS:
            return json_response(fixture('lookupequipment-sem-imagem.json'))
        return json_response(fixture('lookupequipment-vazio.json'))
    if path.endswith('/medium'):
        return httpx.Response(200, content=fixture('camisa.png'), headers={'content-type': 'image/png'})
    return httpx.Response(404, content=b'not found')


def rate_limited(retry_after: str | None = None) -> Handler:
    def handler(_request: httpx.Request) -> httpx.Response:
        headers = {'content-type': 'text/html', **({'retry-after': retry_after} if retry_after else {})}
        return httpx.Response(429, content=fixture('rate-limit-429.html'), headers=headers)

    return handler


def server_error(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, content=b'<h1>500</h1>', headers={'content-type': 'text/html'})


def malformed(_request: httpx.Request) -> httpx.Response:
    return json_response(fixture('malformado.txt'))


async def hanging(_request: httpx.Request) -> httpx.Response:
    await asyncio.sleep(3600)
    raise AssertionError('não deveria chegar aqui')


class Source:
    """Troca o comportamento da fonte sem perder o estado do disjuntor."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.handler: Callable[[httpx.Request], object] = healthy
        self.clock = 1_000_000.0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        result = self.handler(request)
        if asyncio.iscoroutine(result):
            result = await result
        assert isinstance(result, httpx.Response)
        return result

    def api_calls(self) -> list[str]:
        return [c for c in self.calls if '.php' in c]


@pytest_asyncio.fixture
async def source(ctx: AppContext) -> AsyncIterator[Source]:
    await reset_db(ctx.db)
    src = Source()
    ctx.catalog.client = mock_source(src, timeout_ms=200, now=lambda: src.clock)
    yield src


async def age_searches(ctx: AppContext, hours: int) -> None:
    await ctx.db.query("UPDATE catalog_team_searches SET fetched_at = now() - $1 * interval '1 hour'", [hours])


async def age_jerseys(ctx: AppContext, hours: int) -> None:
    await ctx.db.query("UPDATE catalog_teams SET jerseys_fetched_at = now() - $1 * interval '1 hour'", [hours])


# ---------------------------------------------------------------- FR-006/FR-007


async def test_search_teams_devolve_os_times_de_futebol_e_guarda_copia_local(ctx: AppContext, source: Source) -> None:
    res = await search_teams(ctx, 'Fla')
    assert res['source'] == 'live'
    assert 'notice' not in res
    assert [t['name'] for t in res['teams']] == ['Flamengo', 'Flamengo RJ U20']
    first = res['teams'][0]
    assert (first['id'], first['league'], first['country']) == (FLAMENGO, 'Brazilian Serie A', 'Brazil')
    # Vários times e nenhum com o nome exato: só a lista, sem abrir camisas.
    assert res['jerseys'] is None
    assert len(source.api_calls()) == 1
    assert (await ctx.db.query('SELECT 1 FROM catalog_teams')).rowcount == 2


async def test_list_jerseys_devolve_camisas_com_imagens_medium_salvas(ctx: AppContext, source: Source) -> None:
    await search_teams(ctx, 'Fla')
    res = await list_jerseys(ctx, FLAMENGO)
    assert res['source'] == 'live'
    assert len(res['jerseys']) == 2
    first = res['jerseys'][0]
    assert {
        k: first[k] for k in ('team_id', 'team_name', 'league', 'season', 'kind', 'kind_label', 'title', 'image_status')
    } == {
        'team_id': FLAMENGO,
        'team_name': 'Flamengo',
        'league': 'Brazilian Serie A',
        'season': '2019-2020',
        'kind': '1st',
        'kind_label': 'Titular',
        'title': 'Camisa Flamengo 2019-2020 titular',
        'image_status': 'saved',
    }
    assert res['jerseys'][1]['kind_label'] == 'Reserva'

    image_calls = [c for c in source.calls if '/equipment/' in c]
    assert len(image_calls) == 2
    assert all(c.endswith('/medium') for c in image_calls)

    rows = (
        await ctx.db.query('SELECT image_path FROM items WHERE team_external_id = $1 ORDER BY external_id', [FLAMENGO])
    ).rows
    assert len(rows) == 2
    saved = Path(ctx.catalog.storage_dir) / 'images' / rows[0]['image_path']
    assert saved.read_bytes() == fixture('camisa.png')
    assert first['image_url'] == f'/images/{rows[0]["image_path"]}'


async def test_cenario_2_1_um_unico_time_ou_nome_exato_ja_abre_as_camisas(ctx: AppContext, source: Source) -> None:
    single = await search_teams(ctx, 'Palmeiras')
    assert single['selected_team_id'] == PALMEIRAS
    assert len(single['jerseys']) == 2
    assert len(source.api_calls()) == 2

    source.calls.clear()
    exact = await search_teams(ctx, '  FLAMENGO ')
    assert len(exact['teams']) == 2
    assert exact['selected_team_id'] == FLAMENGO
    assert [j['kind'] for j in exact['jerseys']] == ['1st', '2nd']
    assert len(source.api_calls()) == 2


async def test_list_saved_jerseys_traz_so_as_camisas_com_imagem_salva(ctx: AppContext, source: Source) -> None:
    await search_teams(ctx, 'Palmeiras')
    saved = await list_saved_jerseys(ctx)
    assert len(saved['jerseys']) == 1
    j = saved['jerseys'][0]
    assert (j['team_name'], j['kind_label'], j['image_status']) == ('Palmeiras', 'Reserva', 'saved')


# ---------------------------------------------------------------- FR-008


@pytest.mark.parametrize('failure', [server_error, hanging, malformed], ids=['HTTP 500', 'timeout', 'corpo malformado'])
async def test_termo_ja_salvo_responde_do_banco_com_aviso(
    ctx: AppContext, source: Source, failure: Callable[[httpx.Request], object]
) -> None:
    await search_teams(ctx, 'Fla')
    await age_searches(ctx, 25)
    source.handler = failure
    res = await search_teams(ctx, 'fla')
    assert res['source'] == 'cache'
    assert res['notice'] == {'code': 'UPSTREAM_UNAVAILABLE'}
    assert [t['name'] for t in res['teams']] == ['Flamengo', 'Flamengo RJ U20']


async def test_termo_nunca_salvo_responde_lista_vazia_com_o_aviso(ctx: AppContext, source: Source) -> None:
    source.handler = server_error
    res = await search_teams(ctx, 'Corinthians')
    assert (res['source'], res['notice'], res['teams']) == ('cache', {'code': 'UPSTREAM_UNAVAILABLE'}, [])


async def test_camisas_de_um_time_ja_consultado_continuam_com_a_fonte_fora(ctx: AppContext, source: Source) -> None:
    await search_teams(ctx, 'Flamengo')
    await age_jerseys(ctx, 25)
    source.handler = malformed
    res = await list_jerseys(ctx, FLAMENGO)
    assert res['source'] == 'cache'
    assert res['notice'] == {'code': 'UPSTREAM_UNAVAILABLE'}
    assert len(res['jerseys']) == 2


# ---------------------------------------------------------------- FR-008/FR-009


async def test_429_com_retry_after_e_corpo_html_vira_aviso_com_a_espera(ctx: AppContext, source: Source) -> None:
    source.handler = rate_limited('116')
    res = await search_teams(ctx, 'Flamengo')
    assert res['source'] == 'cache'
    assert res['notice']['code'] == 'UPSTREAM_RATE_LIMITED'
    assert 115 <= res['notice']['retry_after_seconds'] <= 116


async def test_com_o_disjuntor_aberto_nenhuma_chamada_sai_ate_a_espera_passar(ctx: AppContext, source: Source) -> None:
    source.handler = rate_limited('116')
    await search_teams(ctx, 'Flamengo')
    source.handler = healthy
    source.calls.clear()

    source.clock += 60_000
    blocked = await search_teams(ctx, 'Palmeiras')
    assert source.calls == []
    assert blocked['notice'] == {'code': 'UPSTREAM_RATE_LIMITED', 'retry_after_seconds': 56}

    source.clock += 57_000
    opened = await search_teams(ctx, 'Palmeiras')
    assert opened['source'] == 'live'
    assert len(source.api_calls()) > 0


async def test_sem_retry_after_assume_120_s(ctx: AppContext, source: Source) -> None:
    source.handler = rate_limited()
    res = await search_teams(ctx, 'Flamengo')
    assert res['notice'] == {'code': 'UPSTREAM_RATE_LIMITED', 'retry_after_seconds': 120}


async def test_termo_consultado_ha_menos_de_24_h_nao_chama_a_fonte(ctx: AppContext, source: Source) -> None:
    await search_teams(ctx, 'Fla')
    source.calls.clear()
    res = await search_teams(ctx, 'FLA')
    assert source.calls == []
    assert res['source'] == 'cache'
    assert 'notice' not in res
    assert len(res['teams']) == 2

    await list_jerseys(ctx, FLAMENGO)
    source.calls.clear()
    await list_jerseys(ctx, FLAMENGO)
    assert source.calls == []


# ---------------------------------------------------------------- casos de borda


async def test_termo_vazio_ou_so_espacos_e_recusado_sem_consultar_a_fonte(ctx: AppContext, source: Source) -> None:
    assert await outcome(search_teams(ctx, '')) == 'VALIDATION'
    assert await outcome(search_teams(ctx, '   ')) == 'VALIDATION'
    assert source.calls == []


async def test_time_sem_camisas_na_fonte_devolve_lista_vazia(ctx: AppContext, source: Source) -> None:
    await search_teams(ctx, 'Fla')
    res = await list_jerseys(ctx, '140112')
    assert res['source'] == 'live'
    assert res['jerseys'] == []


async def test_camisa_sem_url_fica_no_image_falha_no_download_deixa_image_pending(
    ctx: AppContext, source: Source
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/medium'):
            return httpx.Response(503, content=b'erro')
        return healthy(request)

    source.handler = handler
    res = await search_teams(ctx, 'Palmeiras')
    by_kind = {j['kind']: j for j in res['jerseys'] or []}
    assert (by_kind['1st']['image_status'], by_kind['1st']['image_url']) == ('no_image', None)
    assert (by_kind['2nd']['image_status'], by_kind['2nd']['image_url']) == ('image_pending', None)


async def test_time_desconhecido_localmente_not_found_sem_consultar_a_fonte(ctx: AppContext, source: Source) -> None:
    assert await outcome(list_jerseys(ctx, '999')) == 'NOT_FOUND'
    assert source.calls == []
