"""Porte de `cancel.test.ts`: cancelamento de lote sem lances (FR-015, FR-016 da 002)."""

import json
from collections.abc import AsyncIterator
from datetime import datetime

import pytest_asyncio

from leilao.lib.jsjson import iso
from leilao.services.auction import cancel_lot, create_lot, place_bid, settle_due_lots
from leilao.services.audit import list_audit_entries, verify_chain
from leilao.services.context import AppContext, LotCancelledEvent
from leilao.services.wallet import wallet_summary
from tests.helpers import (
    expire_lot,
    gather,
    in_ms,
    lot_input,
    lot_row,
    make_auctioneer,
    make_item,
    make_lot,
    make_user,
    outcome,
    reset_db,
)


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    ctx.events.remove_all_listeners()
    yield


async def db_clock(ctx: AppContext) -> datetime:
    return (await ctx.db.query('SELECT clock_timestamp() AS now')).rows[0]['now']


async def scheduled_lot(ctx: AppContext, auctioneer_id: str) -> str:
    created = await create_lot(
        ctx, auctioneer_id, lot_input(await make_item(ctx), starts_at=in_ms(30 * 60_000), ends_at=in_ms(90 * 60_000))
    )
    return created['id']


async def test_fr015_agendado_e_ao_vivo_sem_lances_sao_cancelados_e_registrados(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    events: list[LotCancelledEvent] = []
    ctx.events.on('lot:cancelled', events.append)

    for lot_id in [await scheduled_lot(ctx, owner['id']), await make_lot(ctx, auctioneer_id=owner['id'])]:
        before = await db_clock(ctx)
        res = await cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=lot_id)
        after = await db_clock(ctx)

        lot = await lot_row(ctx, lot_id)
        assert lot['status'] == 'cancelled'
        assert res['id'] == lot_id and res['status'] == 'cancelled'
        assert before <= lot['cancelled_at'] <= after

        entries = await list_audit_entries(ctx.db, lot_id)
        assert [e['event_type'] for e in entries] == ['lot_opened', 'lot_cancelled']
        assert json.loads(entries[1]['payload_canonical']) == {'at': iso(lot['cancelled_at'])}
        chain = verify_chain(entries, ctx.signer.public_key_pem)
        assert chain['valid'] is True and chain['entries'] == 2
        assert lot['audit_head_hash'] == entries[1]['hash']

        bidder = await make_user(ctx, 10_000)
        assert await outcome(place_bid(ctx, user_id=bidder['id'], lot_id=lot_id, amount_cents=500)) != 'OK'
    assert len(events) == 2


async def test_fr016_recusas_nao_mudam_o_lote(ctx: AppContext) -> None:
    """Com lance, encerrado, já cancelado ou de outro leiloeiro: recusa e não muda o lote."""
    owner = await make_auctioneer(ctx)
    other = await make_auctioneer(ctx)
    bidder = await make_user(ctx, 10_000)

    with_bid = await make_lot(ctx, auctioneer_id=owner['id'])
    await place_bid(ctx, user_id=bidder['id'], lot_id=with_bid, amount_cents=100)
    ended = await make_lot(ctx, auctioneer_id=owner['id'])
    await expire_lot(ctx, ended)
    cancelled = await make_lot(ctx, auctioneer_id=owner['id'])
    await cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=cancelled)
    others_lot = await make_lot(ctx, auctioneer_id=other['id'])

    for lot_id, code in [
        (with_bid, 'LOT_HAS_BIDS'),
        (ended, 'LOT_NOT_CANCELLABLE'),
        (cancelled, 'LOT_NOT_CANCELLABLE'),
        (others_lot, 'NOT_FOUND'),
    ]:
        before = await lot_row(ctx, lot_id)
        assert await outcome(cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=lot_id)) == code
        assert await lot_row(ctx, lot_id) == before


async def test_licitante_nao_cancela(ctx: AppContext) -> None:
    bidder = await make_user(ctx)
    lot_id = await make_lot(ctx)
    assert await outcome(cancel_lot(ctx, auctioneer_id=bidder['id'], lot_id=lot_id)) == 'NOT_FOUND'


async def test_sc005_lance_x_cancelamento_em_paralelo_30_rodadas(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    bidder = await make_user(ctx, 1_000_000)
    totals = {'bid': 0, 'cancel': 0}
    for _ in range(30):
        lot_id = await make_lot(ctx, auctioneer_id=owner['id'])
        bid, cancel = await gather(
            outcome(place_bid(ctx, user_id=bidder['id'], lot_id=lot_id, amount_cents=100)),
            outcome(cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=lot_id)),
        )
        assert [bid, cancel].count('OK') == 1
        totals['bid' if bid == 'OK' else 'cancel'] += 1

        lot = await lot_row(ctx, lot_id)
        count = (await ctx.db.query('SELECT 1 FROM bids WHERE lot_id = $1', [lot_id])).rowcount
        if lot['status'] == 'cancelled':
            assert lot['bid_count'] == 0
            assert count == 0
        else:
            assert count == 1
    assert totals['bid'] + totals['cancel'] == 30


async def test_fr015_lote_cancelado_nao_e_liquidado(ctx: AppContext) -> None:
    """Nem com o fim vencido: sem lançamento e fora do saldo comprometido."""
    owner = await make_auctioneer(ctx)
    bidder = await make_user(ctx, 5_000)
    lot_id = await make_lot(ctx, auctioneer_id=owner['id'])
    await cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=lot_id)
    await expire_lot(ctx, lot_id)

    assert await settle_due_lots(ctx) == 0
    assert (await lot_row(ctx, lot_id))['status'] == 'cancelled'
    assert (await ctx.db.query('SELECT 1 FROM ledger_entries WHERE lot_id = $1', [lot_id])).rowcount == 0
    assert await wallet_summary(ctx.db, bidder['id']) == {
        'balance_cents': 5_000,
        'committed_cents': 0,
        'available_cents': 5_000,
    }
    assert (await wallet_summary(ctx.db, owner['id']))['balance_cents'] == 0
