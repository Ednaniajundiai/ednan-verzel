"""Porte de `realtime.test.ts`: eventos ao vivo da 003 (FR-009, FR-022)."""

from collections.abc import AsyncIterator
from datetime import datetime

import pytest_asyncio
import socketio

from leilao.services.auction import cancel_lot, place_bid
from leilao.services.context import AppContext
from tests.helpers import connect_socket, make_auctioneer, make_lot, make_user, record, reset_db, running_server, sleep

sockets: list[socketio.AsyncClient] = []


@pytest_asyncio.fixture(scope='module')
async def base(ctx: AppContext) -> AsyncIterator[str]:
    async with running_server(ctx, 'jwt-rt') as url:
        yield url
        for s in sockets:
            await s.disconnect()


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    yield


async def client(base: str, lot_id: str | None = None) -> socketio.AsyncClient:
    s = await connect_socket(base, lot_id=lot_id)
    sockets.append(s)
    return s


def ms(iso_text: str) -> int:
    return int(datetime.fromisoformat(iso_text).timestamp() * 1000)


async def test_fr009_lance_que_prorroga_emite_lot_extended_bid_placed_leva_ends_at(ctx: AppContext, base: str) -> None:
    lot_id = await make_lot(ctx, duration_ms=60_000)
    in_room = record(await client(base, lot_id))
    in_list = record(await client(base))
    u = await make_user(ctx, 10_000)
    await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100)
    await sleep(100)

    row = (await ctx.db.query('SELECT ends_at, original_ends_at FROM lots WHERE id = $1', [lot_id])).rows[0]
    ends_ms = int(row['ends_at'].timestamp() * 1000)
    original_ms = int(row['original_ends_at'].timestamp() * 1000)
    for got in (in_room, in_list):
        ext = got['lot:extended'][0]
        assert ext['lot_id'] == lot_id
        assert ms(ext['ends_at']) == ends_ms
        assert ms(ext['previous_ends_at']) == original_ms
        assert ms(got['bid:placed'][0]['ends_at']) == ends_ms


async def test_lance_fora_da_janela_nao_emite_lot_extended(ctx: AppContext, base: str) -> None:
    lot_id = await make_lot(ctx)
    got = record(await client(base, lot_id))
    u = await make_user(ctx, 10_000)
    await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100)
    await sleep(100)
    assert len(got['bid:placed']) == 1
    assert 'lot:extended' not in got


async def test_fr022_lot_cancelled_chega_como_lot_id_na_sala_do_lote_e_em_lots(ctx: AppContext, base: str) -> None:
    owner = await make_auctioneer(ctx)
    lot_id = await make_lot(ctx, auctioneer_id=owner['id'])
    in_room = record(await client(base, lot_id))
    in_list = record(await client(base))
    await cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=lot_id)
    await sleep(100)
    assert in_room['lot:cancelled'] == [{'lot_id': lot_id}]
    assert in_list['lot:cancelled'] == [{'lot_id': lot_id}]
