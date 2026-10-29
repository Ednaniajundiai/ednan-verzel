"""Porte de `wallet-realtime.test.ts`: wallet:changed só para o depositante (FR-012 da 004)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
import socketio

from leilao.http.app import sign_token
from leilao.services.context import AppContext
from leilao.services.wallet import deposit
from tests.helpers import connect_socket, gather, make_user, running_server, sleep

sockets: list[socketio.AsyncClient] = []


@pytest_asyncio.fixture(scope='module')
async def base(ctx: AppContext) -> AsyncIterator[str]:
    async with running_server(ctx, 'jwt-wrt') as url:
        yield url
        for s in sockets:
            await s.disconnect()


async def client(base: str, token: str | None = None) -> list[Any]:
    s = await connect_socket(base, token)
    sockets.append(s)
    got: list[Any] = []
    s.on('wallet:changed', got.append)
    return got


async def test_o_deposito_emite_para_a_sala_user_id_e_para_mais_ninguem(ctx: AppContext, base: str) -> None:
    me, other = await gather(make_user(ctx), make_user(ctx))
    mine = await client(base, sign_token('jwt-wrt', me['id'], 'bidder'))
    theirs = await client(base, sign_token('jwt-wrt', other['id'], 'bidder'))
    anon = await client(base)
    await deposit(ctx, me['id'], 25_000)
    await sleep(100)
    assert mine == [{'balance_cents': 25_000, 'committed_cents': 0, 'available_cents': 25_000}]
    assert theirs == []
    assert anon == []
