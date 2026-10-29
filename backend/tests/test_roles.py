"""Porte de `roles.test.ts`: papel fixo no cadastro e em toda ação autenticada (FR-001 a FR-003 da 002)."""

import secrets
import time
from collections.abc import AsyncIterator
from typing import Any

import jwt
import pytest_asyncio

from leilao.http.app import verify_token
from leilao.services.auction import place_bid
from leilao.services.context import AppContext
from leilao.services.wallet import wallet_summary
from tests.helpers import Api, lot_row, make_auctioneer, make_lot, make_user, outcome, reset_db, running_server

JWT = 'test-jwt-roles'


@pytest_asyncio.fixture(scope='module')
async def api(ctx: AppContext) -> AsyncIterator[Api]:
    async with running_server(ctx, JWT) as base:
        client = Api(base)
        yield client
        await client.close()


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    yield


def person(role: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        'username': f'p-{secrets.token_hex(5)}',
        'password': 'senha-forte-123',
    }
    if role is not None:
        body['role'] = role
    return body


async def test_fr001_cria_a_conta_com_o_papel_escolhido(ctx: AppContext, api: Api) -> None:
    for role in ('auctioneer', 'bidder'):
        status, body = await api('POST', '/auth/register', person(role))
        assert status == 201
        assert body['user']['role'] == role
        res = await ctx.db.query('SELECT role FROM users WHERE id = $1', [body['user']['id']])
        assert res.rows[0]['role'] == role


async def test_fr001_sem_papel_ou_papel_inexistente_e_recusado_apontando_role(api: Api) -> None:
    for payload in (person(), person('admin')):
        status, body = await api('POST', '/auth/register', payload)
        assert status == 400
        assert body['error']['code'] == 'VALIDATION'
        assert 'role' in body['error']['issues']


async def test_fr002_o_token_traz_o_papel_e_me_o_devolve_login_tambem(api: Api) -> None:
    _, reg = await api('POST', '/auth/register', person('auctioneer'))
    assert verify_token(JWT, reg['token']) == {'userId': reg['user']['id'], 'role': 'auctioneer'}
    _, me = await api('GET', '/me', token=reg['token'])
    assert me['user']['role'] == 'auctioneer'

    _, login = await api('POST', '/auth/login', {'username': reg['user']['username'], 'password': 'senha-forte-123'})
    assert login['user']['role'] == 'auctioneer'
    assert (verify_token(JWT, login['token']) or {})['role'] == 'auctioneer'


async def test_fr002_token_no_formato_da_001_sem_role_e_recusado(ctx: AppContext, api: Api) -> None:
    user = await make_user(ctx)
    now = int(time.time())
    legacy = jwt.encode({'iat': now, 'exp': now + 3600, 'sub': user['id']}, JWT, 'HS256')
    assert verify_token(JWT, legacy) is None
    status, body = await api('GET', '/me', token=legacy)
    assert status == 401
    assert body['error']['code'] == 'UNAUTHORIZED'


async def test_fr003_lance_de_leiloeiro_e_recusado_sem_mudar_nada(ctx: AppContext) -> None:
    lot_id = await make_lot(ctx)
    other = await make_auctioneer(ctx)
    before = await lot_row(ctx, lot_id)

    assert (
        await outcome(place_bid(ctx, user_id=other['id'], lot_id=lot_id, amount_cents=500)) == 'AUCTIONEER_CANNOT_BID'
    )

    assert await lot_row(ctx, lot_id) == before
    assert (await ctx.db.query('SELECT 1 FROM bids WHERE lot_id = $1', [lot_id])).rowcount == 0
    assert await wallet_summary(ctx.db, other['id']) == {'balance_cents': 0, 'committed_cents': 0, 'available_cents': 0}


async def test_fr003_pela_api_a_recusa_e_403_com_o_motivo(ctx: AppContext, api: Api) -> None:
    lot_id = await make_lot(ctx)
    _, reg = await api('POST', '/auth/register', person('auctioneer'))
    status, body = await api('POST', f'/lots/{lot_id}/bids', {'amount_cents': 500}, token=reg['token'])
    assert status == 403
    assert body['error'] == {'code': 'AUCTIONEER_CANNOT_BID', 'message': 'Leiloeiros não dão lances'}
