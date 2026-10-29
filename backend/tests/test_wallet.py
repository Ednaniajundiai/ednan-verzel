"""Porte de `wallet.test.ts`: carteira e depósito idempotente (FR-007 a FR-013 da 004)."""

import re
import secrets
from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio

from leilao.services.auction import place_bid
from leilao.services.context import AppContext
from tests.helpers import Api, gather, make_lot, reset_db, running_server


@pytest_asyncio.fixture(scope='module')
async def api(ctx: AppContext) -> AsyncIterator[Api]:
    async with running_server(ctx, 'jwt-wallet') as base:
        client = Api(base)
        yield client
        await client.close()


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    yield


async def account(api: Api, role: str = 'bidder') -> dict[str, Any]:
    _, body = await api(
        'POST',
        '/auth/register',
        {
            'username': f'w-{secrets.token_hex(5)}',
            'password': 'senha-forte-123',
            'role': role,
        },
    )
    return {'id': body['user']['id'], 'auth': {'authorization': f'Bearer {body["token"]}'}}


async def ledger(ctx: AppContext, user_id: str) -> list[dict[str, Any]]:
    res = await ctx.db.query(
        "SELECT amount_cents FROM ledger_entries WHERE user_id = $1 AND kind = 'deposit'", [user_id]
    )
    return res.rows


async def test_get_wallet_total_comprometido_disponivel_e_lotes(ctx: AppContext, api: Api) -> None:
    me = await account(api)
    await api('POST', '/wallet/deposit', {'amount_cents': 100_000}, me['auth'])
    lot_id = await make_lot(ctx)
    await place_bid(ctx, user_id=me['id'], lot_id=lot_id, amount_cents=30_000)

    status, body = await api('GET', '/wallet', headers=me['auth'])
    assert status == 200
    assert body == {
        'balance_cents': 100_000,
        'committed_cents': 30_000,
        'available_cents': 70_000,
        'committed_lots': [{'lot_id': lot_id, 'title': 'Camisa de teste', 'amount_cents': 30_000}],
    }


async def test_deposito_de_250_soma_no_saldo_e_gera_um_lancamento(ctx: AppContext, api: Api) -> None:
    me = await account(api)
    status, body = await api(
        'POST', '/wallet/deposit', {'amount_cents': 25_000}, {**me['auth'], 'idempotency-key': 'dep-1'}
    )
    assert status == 200
    assert body['wallet']['balance_cents'] == 25_000 and body['wallet']['available_cents'] == 25_000
    assert await ledger(ctx, me['id']) == [{'amount_cents': 25_000}]


async def test_fora_dos_limites_400_com_o_limite_e_saldo_intacto(ctx: AppContext, api: Api) -> None:
    me = await account(api)
    for amount in (99, 10_000_001, 0, -500, 150.5):
        status, body = await api('POST', '/wallet/deposit', {'amount_cents': amount}, me['auth'])
        assert status == 400
        assert re.search(r'R\$ 1,00.*R\$ 100\.000,00', body['error']['issues']['amount_cents'][0])
    assert (await api('GET', '/wallet', headers=me['auth']))[1]['balance_cents'] == 0
    assert await ledger(ctx, me['id']) == []


async def test_10_envios_paralelos_com_a_mesma_idempotency_key_um_lancamento(ctx: AppContext, api: Api) -> None:
    me = await account(api)
    results = await gather(
        *(
            api('POST', '/wallet/deposit', {'amount_cents': 50_000}, {**me['auth'], 'idempotency-key': 'duplo-clique'})
            for _ in range(10)
        )
    )
    assert all(status == 200 for status, _ in results)
    assert len([b for _, b in results if not b['replayed']]) == 1
    assert await ledger(ctx, me['id']) == [{'amount_cents': 50_000}]
    assert (await api('GET', '/wallet', headers=me['auth']))[1]['balance_cents'] == 50_000


async def test_fr013_sem_login_401_leiloeiro_403(api: Api) -> None:
    assert (await api('GET', '/wallet'))[0] == 401
    assert (await api('POST', '/wallet/deposit', {'amount_cents': 1_000}))[0] == 401
    seller = await account(api, 'auctioneer')
    assert (await api('GET', '/wallet', headers=seller['auth']))[0] == 403
    assert (await api('POST', '/wallet/deposit', {'amount_cents': 1_000}, seller['auth']))[0] == 403
