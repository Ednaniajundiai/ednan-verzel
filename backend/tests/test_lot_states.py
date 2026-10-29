"""Porte de `lot-states.test.ts`: estado cancelado (FR-019 da 003)."""

from collections.abc import AsyncIterator

import psycopg
import pytest
import pytest_asyncio

from leilao.services.auction import cancel_lot, get_lot, place_bid
from leilao.services.context import AppContext
from leilao.services.wallet import wallet_summary
from tests.helpers import expire_lot, make_auctioneer, make_lot, make_user, outcome, reset_db


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    yield


async def test_restricao_de_status_aceita_cancelled_e_recusa_desconhecido(ctx: AppContext) -> None:
    lot_id = await make_lot(ctx)
    with pytest.raises(psycopg.errors.CheckViolation, match='check'):
        await ctx.db.query("UPDATE lots SET status = 'paused' WHERE id = $1", [lot_id])
    await ctx.db.query("UPDATE lots SET status = 'cancelled', cancelled_at = now() WHERE id = $1", [lot_id])


async def test_cancelar_com_lance_ou_encerrado_e_recusado_ao_vivo_sem_lances_vira_cancelled(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    bidder = await make_user(ctx, 10_000)
    with_bid = await make_lot(ctx, auctioneer_id=owner['id'])
    await place_bid(ctx, user_id=bidder['id'], lot_id=with_bid, amount_cents=100)
    ended = await make_lot(ctx, auctioneer_id=owner['id'])
    await expire_lot(ctx, ended)
    assert await outcome(cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=with_bid)) == 'LOT_HAS_BIDS'
    assert await outcome(cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=ended)) == 'LOT_NOT_CANCELLABLE'

    live = await make_lot(ctx, auctioneer_id=owner['id'])
    await cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=live)
    assert (await get_lot(ctx, live))['phase'] == 'cancelled'
    assert (await wallet_summary(ctx.db, bidder['id']))['committed_cents'] == 100
