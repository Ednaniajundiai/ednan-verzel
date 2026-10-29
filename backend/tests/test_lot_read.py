"""Porte de `lot-read.test.ts`: sala do lote, estados e vitrine (FR-010 a FR-023 da 003)."""

import json
import re
from collections.abc import AsyncIterator
from datetime import datetime

import pytest_asyncio

from leilao.lib.jsjson import iso
from leilao.services.auction import cancel_lot, create_lot, get_lot, list_lots, place_bid, settle_lot
from leilao.services.context import AppContext
from tests.helpers import (
    expire_lot,
    gather,
    lot_input,
    make_auctioneer,
    make_item,
    make_lot,
    make_user,
    reset_db,
    sleep,
    wait_db_clock,
)

HEX16 = r'^[0-9a-f]{16}$'


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    yield


async def lot_starting_in(ctx: AppContext, ms: int, duration_ms: int = 3_600_000) -> tuple[str, str, str]:
    """Lote agendado pelo relógio do banco. Devolve o id, o início e o fim (ISO)."""
    owner = await make_auctioneer(ctx)
    row = (
        await ctx.db.query(
            "SELECT clock_timestamp() + $1 * interval '1 millisecond' AS s, clock_timestamp() + $2 * interval '1 millisecond' AS e",
            [ms, ms + duration_ms],
        )
    ).rows[0]
    starts_at, ends_at = iso(row['s']), iso(row['e'])
    created = await create_lot(ctx, owner['id'], lot_input(await make_item(ctx), starts_at=starts_at, ends_at=ends_at))
    return created['id'], starts_at, ends_at


async def test_lote_ao_vivo_fase_minimo_e_historico_do_mais_recente_ao_mais_antigo(ctx: AppContext) -> None:
    a, b = await gather(make_user(ctx, 10_000), make_user(ctx, 10_000))
    lot_id = await make_lot(ctx, starting_price_cents=1_000, min_increment_cents=100)
    await place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=1_000)
    await place_bid(ctx, user_id=b['id'], lot_id=lot_id, amount_cents=1_100)
    lot = await get_lot(ctx, lot_id)
    assert lot['phase'] == 'live'
    assert lot['result'] is None
    assert lot['next_minimum_cents'] == 1_200
    assert lot['current_price_cents'] == 1_100
    assert lot['extended'] is False
    assert [x['amount_cents'] for x in lot['bids']] == [1_100, 1_000]
    assert re.match(HEX16, lot['bids'][0]['bidder'])
    assert isinstance(lot['bids'][0]['at'], str)
    assert lot['original_ends_at'] == lot['ends_at']


async def test_standings_de_todos_e_viewer_so_para_quem_esta_logado(ctx: AppContext) -> None:
    users = await gather(*(make_user(ctx, 100_000) for _ in range(5)))
    lot_id = await make_lot(ctx, starting_price_cents=100, min_increment_cents=10)
    # u0 100, u1 110, u2 120, u3 130, u4 140, depois u1 150 → maiores: u1 150, u4 140, u3 130, u2 120, u0 100
    for i, amount in [(0, 100), (1, 110), (2, 120), (3, 130), (4, 140), (1, 150)]:
        await place_bid(ctx, user_id=users[i]['id'], lot_id=lot_id, amount_cents=amount)
    anon = await get_lot(ctx, lot_id)
    assert [s['max_cents'] for s in anon['standings']] == [150, 140, 130, 120, 100]
    assert 'viewer' not in anon

    second = await get_lot(ctx, lot_id, users[4]['id'])
    assert second['viewer'] == {
        'bidder': second['standings'][1]['bidder'],
        'has_bid': True,
        'position': 2,
        'total_bidders': 5,
        'leading': False,
    }
    leader = await get_lot(ctx, lot_id, users[1]['id'])
    assert leader['viewer']['position'] == 1 and leader['viewer']['leading'] is True
    # O pseudônimo do próprio usuário marca "você" no histórico.
    assert [x['amount_cents'] for x in leader['bids'] if x['bidder'] == leader['viewer']['bidder']] == [150, 110]

    newcomer = await make_user(ctx, 100)
    viewer = (await get_lot(ctx, lot_id, newcomer['id']))['viewer']
    assert viewer['has_bid'] is False and viewer['position'] is None
    assert viewer['total_bidders'] == 5 and viewer['leading'] is False

    body = json.dumps([anon, second, leader])
    for u in users:
        assert u['id'] not in body
        assert u['username'] not in body


async def test_fr015_encerrado_devolve_result_sold_ou_unsold(ctx: AppContext) -> None:
    u = await make_user(ctx, 10_000)
    sold = await make_lot(ctx)
    await place_bid(ctx, user_id=u['id'], lot_id=sold, amount_cents=100)
    await expire_lot(ctx, sold)
    unsold = await make_lot(ctx)
    await expire_lot(ctx, unsold)
    s = await get_lot(ctx, sold)
    assert (s['phase'], s['result'], s['status']) == ('ended', 'sold', 'settled')
    n = await get_lot(ctx, unsold)
    assert (n['phase'], n['result']) == ('ended', 'unsold')


async def test_fr018_agendado_ao_vivo_encerrado_pelo_horario_sem_acao_manual(ctx: AppContext) -> None:
    """Sem `sleep` fixo (spec 005, FR-019): 1,5 s de margem em cada fase e espera pelo relógio do
    banco antes de cada afirmação. Antes oscilava quando a criação passava de ~300 ms."""
    lot_id, starts_at, ends_at = await lot_starting_in(ctx, 1_500, 1_500)
    assert (await get_lot(ctx, lot_id))['phase'] == 'scheduled'
    await wait_db_clock(ctx, starts_at, margin_ms=50)
    assert (await get_lot(ctx, lot_id))['phase'] == 'live'
    await wait_db_clock(ctx, ends_at, margin_ms=50)
    assert (await get_lot(ctx, lot_id))['phase'] == 'ended'


async def test_fr020_fr021_vitrine_nunca_lista_cancelado_cartao_por_fase_ordem_d14(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    u = await make_user(ctx, 10_000)
    live_late = await make_lot(ctx, duration_ms=600_000)
    live_soon = await make_lot(ctx, duration_ms=300_000)
    await place_bid(ctx, user_id=u['id'], lot_id=live_soon, amount_cents=100)
    sched_late, _, _ = await lot_starting_in(ctx, 1_200_000)
    sched_soon, _, _ = await lot_starting_in(ctx, 600_000)
    ended_old = await make_lot(ctx)
    await expire_lot(ctx, ended_old)
    await settle_lot(ctx, ended_old)
    await sleep(5)
    ended_new = await make_lot(ctx)
    await place_bid(ctx, user_id=u['id'], lot_id=ended_new, amount_cents=100)
    await expire_lot(ctx, ended_new)  # vencido e ainda não liquidado: a vitrine liquida na leitura
    cancelled = await make_lot(ctx, auctioneer_id=owner['id'])
    await cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=cancelled)

    lots = await list_lots(ctx)
    assert cancelled not in [lot['id'] for lot in lots]
    assert [(lot['id'], lot['phase']) for lot in lots] == [
        (live_soon, 'live'),
        (live_late, 'live'),
        (sched_soon, 'scheduled'),
        (sched_late, 'scheduled'),
        (ended_new, 'ended'),
        (ended_old, 'ended'),
    ]
    by_id = {lot['id']: lot for lot in lots}
    assert by_id[live_soon]['current_price_cents'] == 100 and isinstance(by_id[live_soon]['ends_at'], str)
    assert by_id[sched_soon]['starting_price_cents'] == 100 and isinstance(by_id[sched_soon]['starts_at'], str)
    assert by_id[ended_new]['result'] == 'sold' and by_id[ended_new]['current_price_cents'] == 100
    assert by_id[ended_old]['result'] == 'unsold'


async def test_fr023_get_lot_de_lote_cancelado_devolve_phase_cancelled(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    lot_id = await make_lot(ctx, auctioneer_id=owner['id'])
    await cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=lot_id)
    lot = await get_lot(ctx, lot_id)
    assert (lot['phase'], lot['status'], lot['result']) == ('cancelled', 'cancelled', None)


async def test_extended_fim_vigente_maior_que_o_original(ctx: AppContext) -> None:
    u = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx, duration_ms=60_000)
    await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100)
    lot = await get_lot(ctx, lot_id)
    assert lot['extended'] is True
    assert datetime.fromisoformat(lot['ends_at']) > datetime.fromisoformat(lot['original_ends_at'])
