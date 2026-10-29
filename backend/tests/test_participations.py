"""Porte de `participations.test.ts`: meus arremates (FR-013 a FR-015 da 004)."""

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio

from leilao.http.app import sign_token
from leilao.services.auction import place_bid
from leilao.services.context import AppContext, LotRules
from leilao.services.receipts import receipt_id
from tests.helpers import Api, gather, make_auctioneer, make_lot, make_user, reset_db, running_server, sleep

JWT = 'jwt-part'


@pytest_asyncio.fixture(scope='module')
async def api(ctx: AppContext) -> AsyncIterator[Api]:
    async with running_server(ctx, JWT) as base:
        client = Api(base)
        yield client
        await client.close()


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    ctx.rules = LotRules(extension_window_ms=0, extension_ms=0)
    yield


async def participations(api: Api, user_id: str, role: str = 'bidder') -> tuple[int, Any]:
    res = await api.get('/me/participations', headers={'authorization': f'Bearer {sign_token(JWT, user_id, role)}'})
    return res.status_code, res.json()


async def test_participando_arrematado_com_comprovante_e_nao_arrematado(ctx: AppContext, api: Api) -> None:
    me, rival = await gather(make_user(ctx, 100_000), make_user(ctx, 100_000))
    live = await make_lot(ctx)
    await place_bid(ctx, user_id=me['id'], lot_id=live, amount_cents=100)
    await place_bid(ctx, user_id=rival['id'], lot_id=live, amount_cents=200)

    won = await make_lot(ctx, duration_ms=300)
    lost = await make_lot(ctx, duration_ms=300)
    await place_bid(ctx, user_id=me['id'], lot_id=won, amount_cents=700)
    await place_bid(ctx, user_id=me['id'], lot_id=lost, amount_cents=100)
    await place_bid(ctx, user_id=rival['id'], lot_id=lost, amount_cents=900)
    await sleep(350)  # encerram sozinhos; a leitura liquida (Const. 3.3)

    status, body = await participations(api, me['id'])
    assert status == 200
    assert body['server_now']
    (p,) = body['participating']
    assert {k: p[k] for k in ('lot_id', 'phase', 'current_price_cents', 'my_max_cents', 'leading')} == {
        'lot_id': live,
        'phase': 'live',
        'current_price_cents': 200,
        'my_max_cents': 100,
        'leading': False,
    }
    assert isinstance(p['ends_at'], str)
    closed = {c['lot_id']: c for c in body['closed']}
    assert {k: closed[won][k] for k in ('outcome', 'final_price_cents', 'my_max_cents', 'receipt_url')} == {
        'outcome': 'won',
        'final_price_cents': 700,
        'my_max_cents': 700,
        'receipt_url': f'/comprovante/{receipt_id("test-receipt-secret", won)}',
    }
    assert {k: closed[lost][k] for k in ('outcome', 'final_price_cents', 'my_max_cents')} == {
        'outcome': 'lost',
        'final_price_cents': 900,
        'my_max_cents': 100,
    }
    assert 'receipt_url' not in closed[lost]

    text = json.dumps(body)
    assert rival['id'] not in text
    assert rival['username'] not in text
    assert me['id'] not in text


async def test_quem_nunca_deu_lance_recebe_listas_vazias(ctx: AppContext, api: Api) -> None:
    me = await make_user(ctx)
    _, body = await participations(api, me['id'])
    assert (body['participating'], body['closed']) == ([], [])


async def test_sem_login_401_leiloeiro_403(ctx: AppContext, api: Api) -> None:
    assert (await api.get('/me/participations')).status_code == 401
    seller = await make_auctioneer(ctx)
    assert (await participations(api, seller['id'], 'auctioneer'))[0] == 403
