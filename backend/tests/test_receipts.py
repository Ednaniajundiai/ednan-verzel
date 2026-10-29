"""Porte de `receipts.test.ts`: comprovante público (FR-017 a FR-022 da 004)."""

import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import pytest_asyncio

from leilao.services.auction import cancel_lot, place_bid, settle_lot
from leilao.services.audit import list_audit_entries
from leilao.services.context import AppContext, LotRules
from leilao.services.receipts import receipt_code, receipt_id
from leilao.services.thesportsdb import TheSportsDbClient
from tests.helpers import Api, gather, make_auctioneer, make_lot, make_user, reset_db, running_server, sleep

SECRET = 'test-receipt-secret'


@pytest_asyncio.fixture(scope='module')
async def api(ctx: AppContext) -> AsyncIterator[Api]:
    ctx.catalog.client = TheSportsDbClient('http://127.0.0.1:9/api/v1/json/123', timeout_ms=200)
    async with running_server(ctx, 'jwt-rcpt') as base:
        client = Api(base)
        yield client
        await client.close()


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    ctx.rules = LotRules(extension_window_ms=0, extension_ms=0)
    yield


async def get(api: Api, path: str) -> tuple[int, Any]:
    res = await api.get(path)
    return res.status_code, res.json()


async def sold_lot(ctx: AppContext) -> str:
    winner, other = await gather(make_user(ctx, 100_000), make_user(ctx, 100_000))
    lot_id = await make_lot(ctx, duration_ms=300)
    await place_bid(ctx, user_id=other['id'], lot_id=lot_id, amount_cents=1_000)
    await place_bid(ctx, user_id=winner['id'], lot_id=lot_id, amount_cents=4_500)
    await sleep(350)
    await settle_lot(ctx, lot_id)
    await sleep(20)
    return lot_id


async def test_lote_liquidado_com_vencedor_comprovante_completo_sem_login(ctx: AppContext, api: Api) -> None:
    lot_id = await sold_lot(ctx)
    status, body = await get(api, f'/receipts/{receipt_id(SECRET, lot_id)}')
    assert status == 200
    assert body['receipt_id'] == receipt_id(SECRET, lot_id)
    assert body['code'] == receipt_code(SECRET, lot_id)
    lot = body['lot']
    assert (lot['id'], lot['number'], lot['title'], lot['image_url'], lot['size']) == (
        lot_id,
        lot_id[:8].upper(),
        'Camisa de teste',
        '/images/teste.png',
        'M',
    )
    assert body['final_price_cents'] == 4_500
    assert isinstance(body['settled_at'], str)
    assert body['verdict']['verdict'] == 'intact' and body['verdict']['failure_kind'] is None
    assert body['tampered'] is False
    assert body['audit_url'] == f'/auditoria/{lot_id}'
    # FR-021: o mesmo pseudônimo do lance vencedor na auditoria.
    bids = [e for e in await list_audit_entries(ctx.db, lot_id) if e['event_type'] == 'bid_placed']
    assert body['winner'] == json.loads(bids[-1]['payload_canonical'])['bidder']


async def test_token_alterado_ou_id_malformado_404(ctx: AppContext, api: Api) -> None:
    lot_id = await sold_lot(ctx)
    rid = receipt_id(SECRET, lot_id)
    flipped = rid[:-1] + ('B' if rid.endswith('A') else 'A')
    for bad in (flipped, lot_id, 'qualquer-coisa', f'{lot_id}.curto'):
        assert (await get(api, f'/receipts/{quote(bad, safe="")}'))[0] == 404


async def test_sem_lances_cancelado_ou_ainda_nao_liquidado_404(ctx: AppContext, api: Api) -> None:
    owner = await make_auctioneer(ctx)
    unsold = await make_lot(ctx, duration_ms=200)
    await sleep(250)
    await settle_lot(ctx, unsold)
    cancelled = await make_lot(ctx, auctioneer_id=owner['id'])
    await cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=cancelled)
    u = await make_user(ctx, 10_000)
    open_lot = await make_lot(ctx)
    await place_bid(ctx, user_id=u['id'], lot_id=open_lot, amount_cents=100)
    for lot_id in (unsold, cancelled, open_lot):
        assert (await get(api, f'/receipts/{receipt_id(SECRET, lot_id)}'))[0] == 404


async def test_historico_adulterado_depois_do_encerramento_o_comprovante_mostra_o_aviso(
    ctx: AppContext, api: Api
) -> None:
    lot_id = await sold_lot(ctx)
    await ctx.db.query('ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_update')
    try:
        await ctx.db.query(
            """UPDATE audit_log SET payload_canonical = replace(payload_canonical, '"amount_cents":1000', '"amount_cents":1') WHERE lot_id = $1 AND seq = 2""",
            [lot_id],
        )
    finally:
        await ctx.db.query('ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_update')
    _, body = await get(api, f'/receipts/{receipt_id(SECRET, lot_id)}')
    assert body['tampered'] is True
    assert body['verdict']['verdict'] == 'tampered' and body['verdict']['failure_kind'] == 'altered'
    assert body['final_price_cents'] == 4_500
