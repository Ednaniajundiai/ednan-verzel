"""Porte de `antisniping.test.ts`: prorrogação anti-sniping (FR-006, FR-007 da 003)."""

import asyncio
import itertools
import random
from collections.abc import AsyncIterator

import pytest_asyncio

from leilao.services.auction import in_extension_window, place_bid
from leilao.services.context import AppContext, LotRules
from tests.helpers import gather, lot_row, make_lot, make_user, outcome, reset_db, sleep


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    ctx.rules = LotRules()
    yield


async def ends_at_is_bid_plus_extension(ctx: AppContext, lot_id: str, bid_id: int, extension_ms: int) -> bool:
    """Compara no banco, em µs: fim vigente = instante do lance + prorrogação."""
    res = await ctx.db.query(
        """SELECT l.ends_at = b.created_at + $3 * interval '1 millisecond' AS ok
       FROM lots l JOIN bids b ON b.lot_id = l.id WHERE l.id = $1 AND b.id = $2""",
        [lot_id, bid_id, extension_ms],
    )
    return bool(res.rows[0]['ok'])


async def test_sc002_lance_com_menos_de_2_min_fim_vira_lance_mais_2_min(ctx: AppContext) -> None:
    u = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx, duration_ms=60_000)
    before = await lot_row(ctx, lot_id)
    bid = await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100)
    assert await ends_at_is_bid_plus_extension(ctx, lot_id, bid.bid_id, 120_000)
    after = await lot_row(ctx, lot_id)
    assert after['ends_at'] > before['ends_at']
    assert after['original_ends_at'] == before['original_ends_at']


async def test_lance_com_mais_de_2_min_para_o_fim_nao_mexe_no_fim(ctx: AppContext) -> None:
    u = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx)  # 1 h
    before = await lot_row(ctx, lot_id)
    await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100)
    assert (await lot_row(ctx, lot_id))['ends_at'] == before['ends_at']


async def test_exatamente_2_min_para_o_fim_conta_como_ultimos_2_minutos(ctx: AppContext) -> None:
    ends = '2026-10-28T20:00:00.000000Z'
    assert await in_extension_window(ctx.db, '2026-10-28T19:58:00.000000Z', ends, 120_000) is True
    assert await in_extension_window(ctx.db, '2026-10-28T19:57:59.999999Z', ends, 120_000) is False
    assert await in_extension_window(ctx.db, '2026-10-28T19:58:30.000000Z', ends, 120_000) is True


async def test_sc003_lance_decidido_depois_do_fim_ja_prorrogado_lot_ended(ctx: AppContext) -> None:
    ctx.rules = LotRules(extension_window_ms=300, extension_ms=300)
    a, b = await gather(make_user(ctx, 10_000), make_user(ctx, 10_000))
    lot_id = await make_lot(ctx, duration_ms=200)
    first = await place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=100)
    assert await ends_at_is_bid_plus_extension(ctx, lot_id, first.bid_id, 300)
    await sleep(450)
    assert await outcome(place_bid(ctx, user_id=b['id'], lot_id=lot_id, amount_cents=1_000)) == 'LOT_ENDED'


async def test_sc004_50_lances_simultaneos_na_janela_fim_nunca_diminui(ctx: AppContext) -> None:
    """SC-004: fim = maior instante aceito + 2 min, e nunca diminui."""
    users = await gather(*(make_user(ctx, 1_000_000) for _ in range(50)))
    lot_id = await make_lot(ctx, duration_ms=60_000, starting_price_cents=100, min_increment_cents=10)
    amounts = [100 + i * 10 for i in range(len(users))]
    random.shuffle(amounts)

    seen: list[int] = []
    stop = False

    async def watcher() -> None:
        while not stop:
            res = await ctx.db.query(
                'SELECT (extract(epoch FROM ends_at) * 1000000)::bigint::text AS us FROM lots WHERE id = $1', [lot_id]
            )
            seen.append(int(res.rows[0]['us']))
            await sleep(2)

    watching = asyncio.create_task(watcher())
    results = await gather(
        *(outcome(place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=amounts[i])) for i, u in enumerate(users))
    )
    stop = True
    await watching

    assert all(r in ('OK', 'BID_TOO_LOW') for r in results)
    for prev, cur in itertools.pairwise(seen):
        assert cur >= prev
    res = await ctx.db.query(
        """SELECT l.ends_at = (SELECT max(created_at) FROM bids WHERE lot_id = l.id) + interval '2 minutes' AS ok
         FROM lots l WHERE l.id = $1""",
        [lot_id],
    )
    assert res.rows[0]['ok'] is True
