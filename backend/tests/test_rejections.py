"""Porte de `rejections.test.ts`: motivos de recusa (FR-001 a FR-005 e FR-025 da 003)."""

from collections.abc import AsyncIterator, Awaitable
from datetime import datetime
from typing import Any

import pytest_asyncio

from leilao.lib.errors import AppError
from leilao.lib.jsjson import iso
from leilao.services.auction import cancel_lot, create_lot, place_bid, settle_lot
from leilao.services.context import AppContext
from tests.helpers import (
    expire_lot,
    gather,
    in_ms,
    lot_input,
    make_auctioneer,
    make_item,
    make_lot,
    make_user,
    reset_db,
)


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    yield


async def refusal(aw: Awaitable[Any]) -> dict[str, Any]:
    """Código, mensagem e detalhes da recusa (ou OK)."""
    try:
        await aw
        return {'code': 'OK'}
    except AppError as err:
        return {'code': err.code, 'message': err.message, 'details': err.details}


async def scheduled_lot(ctx: AppContext) -> dict[str, Any]:
    owner = await make_auctioneer(ctx)
    starts_at = in_ms(30 * 60_000)
    created = await create_lot(
        ctx, owner['id'], lot_input(await make_item(ctx), starts_at=starts_at, ends_at=in_ms(90 * 60_000))
    )
    return {'id': created['id'], 'owner': owner, 'starts_at': starts_at}


async def cancelled_lot(ctx: AppContext) -> str:
    owner = await make_auctioneer(ctx)
    lot_id = await make_lot(ctx, auctioneer_id=owner['id'])
    await cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=lot_id)
    return lot_id


async def test_fr001_lote_agendado_lot_not_started_com_o_horario_de_inicio(ctx: AppContext) -> None:
    lot = await scheduled_lot(ctx)
    bidder = await make_user(ctx, 10_000)
    r = await refusal(place_bid(ctx, user_id=bidder['id'], lot_id=lot['id'], amount_cents=500))
    assert r['code'] == 'LOT_NOT_STARTED'
    assert r['message'] == 'Este lote ainda não começou'
    assert iso(datetime.fromisoformat(r['details']['starts_at'])) == lot['starts_at']


async def test_fr002_fim_ja_passou_lot_ended_liquidado_tambem(ctx: AppContext) -> None:
    bidder = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx)
    await expire_lot(ctx, lot_id)
    r = await refusal(place_bid(ctx, user_id=bidder['id'], lot_id=lot_id, amount_cents=500))
    assert (r['code'], r['message']) == ('LOT_ENDED', 'Este lote já foi encerrado')
    await settle_lot(ctx, lot_id)
    assert (await refusal(place_bid(ctx, user_id=bidder['id'], lot_id=lot_id, amount_cents=500)))['code'] == 'LOT_ENDED'


async def test_fr003_lote_cancelado_lot_cancelled(ctx: AppContext) -> None:
    bidder = await make_user(ctx, 10_000)
    r = await refusal(place_bid(ctx, user_id=bidder['id'], lot_id=await cancelled_lot(ctx), amount_cents=500))
    assert (r['code'], r['message']) == ('LOT_CANCELLED', 'Este lote foi cancelado')


async def test_fr004_ja_ganhando_abaixo_do_minimo_e_saldo_insuficiente(ctx: AppContext) -> None:
    a, b = await gather(make_user(ctx, 100_000), make_user(ctx, 5_000))
    lot_id = await make_lot(ctx, starting_price_cents=10_000, min_increment_cents=1_000)
    await place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=10_000)

    r = await refusal(place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=20_000))
    assert (r['code'], r['message']) == ('ALREADY_LEADING', 'Você já está ganhando este lote')
    r = await refusal(place_bid(ctx, user_id=b['id'], lot_id=lot_id, amount_cents=10_500))
    assert r == {'code': 'BID_TOO_LOW', 'message': 'Lance abaixo do mínimo', 'details': {'minimum_cents': 11_000}}
    r = await refusal(place_bid(ctx, user_id=b['id'], lot_id=lot_id, amount_cents=11_000))
    assert r == {'code': 'INSUFFICIENT_FUNDS', 'message': 'Saldo insuficiente', 'details': {'available_cents': 5_000}}


async def test_fr005_cancelado_e_abaixo_do_minimo_lot_cancelled(ctx: AppContext) -> None:
    bidder = await make_user(ctx, 10_000)
    r = await refusal(place_bid(ctx, user_id=bidder['id'], lot_id=await cancelled_lot(ctx), amount_cents=1))
    assert r['code'] == 'LOT_CANCELLED'


async def test_fr005_agendado_e_saldo_insuficiente_lot_not_started(ctx: AppContext) -> None:
    poor = await make_user(ctx, 0)
    lot = await scheduled_lot(ctx)
    r = await refusal(place_bid(ctx, user_id=poor['id'], lot_id=lot['id'], amount_cents=100_000))
    assert r['code'] == 'LOT_NOT_STARTED'


async def test_fr005_encerrado_e_ja_ganhando_lot_ended(ctx: AppContext) -> None:
    a = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx)
    await place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=100)
    await expire_lot(ctx, lot_id)
    assert (await refusal(place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=1_000)))['code'] == 'LOT_ENDED'


async def test_fr025_leiloeiro_recebe_auctioneer_cannot_bid_antes_de_qualquer_motivo(ctx: AppContext) -> None:
    auctioneer = await make_auctioneer(ctx)
    ended = await make_lot(ctx)
    await expire_lot(ctx, ended)
    for lot_id in [await cancelled_lot(ctx), ended, (await scheduled_lot(ctx))['id'], await make_lot(ctx)]:
        r = await refusal(place_bid(ctx, user_id=auctioneer['id'], lot_id=lot_id, amount_cents=1))
        assert (r['code'], r['message']) == ('AUCTIONEER_CANNOT_BID', 'Leiloeiros não dão lances')
