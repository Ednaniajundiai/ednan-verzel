"""Porte de `privacy.test.ts`: nenhuma superfície pública expõe dado pessoal (FR-020, FR-027, SC-002 da 004)."""

import json
import re
from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio

from leilao.services.auction import cancel_lot, place_bid, settle_lot
from leilao.services.context import AppContext, LotRules
from leilao.services.receipts import receipt_id
from tests.helpers import Api, connect_socket, gather, make_auctioneer, make_lot, make_user, running_server, sleep


@pytest_asyncio.fixture(scope='module')
async def base(ctx: AppContext) -> AsyncIterator[str]:
    async with running_server(ctx, 'jwt-priv') as url:
        yield url


async def test_auditoria_verificacao_comprovante_e_eventos_publicos_so_tem_pseudonimos(
    ctx: AppContext, base: str
) -> None:
    owner = await make_auctioneer(ctx)
    ana, bruno = await gather(make_user(ctx, 100_000), make_user(ctx, 100_000))
    listener = await connect_socket(base)
    events: list[dict[str, Any]] = []

    async def on_any(name: str, *args: Any) -> None:
        events.append({'name': name, 'payload': args[0] if args else None})

    listener.on('*', on_any)

    ctx.rules = LotRules(extension_window_ms=60_000, extension_ms=1_000)  # gera também lot:extended
    lot_id = await make_lot(ctx, duration_ms=400, auctioneer_id=owner['id'])
    await place_bid(ctx, user_id=ana['id'], lot_id=lot_id, amount_cents=100)
    await place_bid(ctx, user_id=bruno['id'], lot_id=lot_id, amount_cents=200)
    await sleep(1_300)
    await settle_lot(ctx, lot_id)
    to_cancel = await make_lot(ctx, auctioneer_id=owner['id'])
    await cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=to_cancel)
    await sleep(100)

    api = Api(base)
    bodies: list[str] = []
    for path in (
        f'/audit/lots/{lot_id}',
        f'/audit/lots/{lot_id}/verify',
        f'/receipts/{receipt_id("test-receipt-secret", lot_id)}',
        f'/lots/{lot_id}',
    ):
        res = await api.get(path)
        assert res.status_code == 200
        bodies.append(res.text)
    await api.close()

    everything = '\n'.join([*bodies, json.dumps(events)])
    names = {e['name'] for e in events}
    assert {'bid:placed', 'lot:extended', 'lot:settled', 'lot:cancelled'} <= names
    for u in (owner, ana, bruno):
        assert u['id'] not in everything
        assert u['username'] not in everything
        assert u['name'] not in everything
    assert not re.search(
        'auctioneer_id|leader_user_id|winnerUserId|outbidUserId|winner_user_id|outbid_user_id', everything
    )
    await listener.disconnect()
