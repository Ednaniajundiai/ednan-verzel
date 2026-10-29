"""Porte de `auctioneer-panel.test.ts`: resultados e total recebido (FR-005, FR-017, FR-018 da 002)."""

from collections.abc import AsyncIterator

import pytest_asyncio

from leilao.services.auction import cancel_lot, list_auctioneer_lots, place_bid, settle_lot
from leilao.services.context import AppContext
from tests.helpers import expire_lot, make_auctioneer, make_lot, make_user, reset_db


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    yield


async def sold(ctx: AppContext, auctioneer_id: str, price: int, settle: bool = True) -> str:
    winner = await make_user(ctx, 1_000_000)
    lot_id = await make_lot(ctx, auctioneer_id=auctioneer_id)
    await place_bid(ctx, user_id=winner['id'], lot_id=lot_id, amount_cents=price)
    await expire_lot(ctx, lot_id)
    if settle:
        await settle_lot(ctx, lot_id)
    return lot_id


def subset(actual: dict[str, object], expected: dict[str, object]) -> bool:
    return all(actual.get(k) == v for k, v in expected.items())


async def test_rotulos_por_lote_e_total_so_dos_arrematados(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    sold_a = await sold(ctx, owner['id'], 12_000)
    sold_b = await sold(ctx, owner['id'], 3_500)
    unsold = await make_lot(ctx, auctioneer_id=owner['id'])
    await expire_lot(ctx, unsold)
    await settle_lot(ctx, unsold)
    cancelled = await make_lot(ctx, auctioneer_id=owner['id'])
    await cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=cancelled)
    open_lot = await make_lot(ctx, auctioneer_id=owner['id'])

    panel = await list_auctioneer_lots(ctx, owner['id'])
    by_id = {lot['id']: lot for lot in panel['lots']}
    assert subset(
        by_id[sold_a], {'outcome': 'sold', 'final_price_cents': 12_000, 'phase': 'ended', 'can_cancel': False}
    )
    assert subset(by_id[sold_b], {'outcome': 'sold', 'final_price_cents': 3_500})
    assert subset(by_id[unsold], {'outcome': 'unsold', 'final_price_cents': None})
    assert subset(by_id[cancelled], {'outcome': 'cancelled', 'phase': 'cancelled', 'can_cancel': False})
    assert subset(by_id[open_lot], {'outcome': 'open', 'phase': 'live', 'can_cancel': True})
    assert panel['total_received_cents'] == 15_500


async def test_lote_com_lance_ainda_aberto_nao_pode_ser_cancelado_pelo_painel(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    bidder = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx, auctioneer_id=owner['id'])
    await place_bid(ctx, user_id=bidder['id'], lot_id=lot_id, amount_cents=300)
    (lot,) = (await list_auctioneer_lots(ctx, owner['id']))['lots']
    assert subset(lot, {'outcome': 'open', 'current_price_cents': 300, 'bid_count': 1, 'can_cancel': False})


async def test_fr017_lote_vencido_e_ainda_aberto_ja_aparece_encerrado_com_o_credito(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    lot_id = await sold(ctx, owner['id'], 9_900, settle=False)
    panel = await list_auctioneer_lots(ctx, owner['id'])
    assert subset(panel['lots'][0], {'id': lot_id, 'outcome': 'sold', 'final_price_cents': 9_900, 'phase': 'ended'})
    assert panel['total_received_cents'] == 9_900


async def test_fr005_o_painel_de_a_nao_lista_lotes_de_b(ctx: AppContext) -> None:
    a = await make_auctioneer(ctx)
    b = await make_auctioneer(ctx)
    lot_a = await make_lot(ctx, auctioneer_id=a['id'])
    await sold(ctx, b['id'], 5_000)
    panel = await list_auctioneer_lots(ctx, a['id'])
    assert [lot['id'] for lot in panel['lots']] == [lot_a]
    assert panel['total_received_cents'] == 0
