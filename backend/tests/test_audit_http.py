"""Porte de `audit-http.test.ts`: rotas públicas de auditoria (FR-001 a FR-003, FR-006 da 004)."""

import json
import re
from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio

from leilao.services.auction import place_bid
from leilao.services.context import AppContext
from leilao.services.thesportsdb import TheSportsDbClient
from tests.helpers import Api, make_lot, make_user, reset_db, running_server, sleep


@pytest_asyncio.fixture(scope='module')
async def api(ctx: AppContext) -> AsyncIterator[Api]:
    # Fonte externa apontando para um endereço inválido: nada aqui pode depender dela (FR-006).
    ctx.catalog.client = TheSportsDbClient('http://127.0.0.1:9/api/v1/json/123', timeout_ms=200)
    async with running_server(ctx, 'jwt-audit') as base:
        client = Api(base)
        yield client
        await client.close()


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    yield


async def get(api: Api, path: str) -> tuple[int, Any]:
    res = await api.get(path)
    return res.status_code, res.json()


async def test_get_audit_lot_sem_login_entries_lot_witness_e_verdict(ctx: AppContext, api: Api) -> None:
    u = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx)
    await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100)
    await sleep(20)

    status, body = await get(api, f'/audit/lots/{lot_id}')
    assert status == 200
    assert body['lot_id'] == lot_id and body['algorithm'] == 'sha256+ed25519'
    assert [e['event_type'] for e in body['entries']] == ['lot_opened', 'bid_placed']
    bid = json.loads(body['entries'][1]['payload_canonical'])
    assert bid['amount_cents'] == 100 and re.fullmatch(r'[0-9a-f]{16}', bid['bidder']) and isinstance(bid['at'], str)
    lot = body['lot']
    assert (lot['id'], lot['title'], lot['image_url'], lot['status'], lot['phase']) == (
        lot_id,
        'Camisa de teste',
        '/images/teste.png',
        'open',
        'live',
    )
    assert body['witness']['seq'] == 2 and body['witness']['head_hash'] == body['entries'][1]['hash']
    v = body['verdict']
    assert (v['verdict'], v['failure_kind'], v['witness_ok']) == ('intact', None, True)


async def test_lote_inexistente_404_nas_duas_rotas(api: Api) -> None:
    lot_id = '00000000-0000-4000-8000-000000000000'
    assert (await get(api, f'/audit/lots/{lot_id}'))[0] == 404
    assert (await get(api, f'/audit/lots/{lot_id}/verify'))[0] == 404


async def test_verify_mantem_os_campos_anteriores_e_acrescenta_failure_kind_e_witness_ok(
    ctx: AppContext, api: Api
) -> None:
    lot_id = await make_lot(ctx)
    await sleep(20)
    _, body = await get(api, f'/audit/lots/{lot_id}/verify')
    expected = {
        'valid': True,
        'entries': 1,
        'head_matches_lot': True,
        'ends_at_mismatch': False,
        'failure_kind': None,
        'witness_ok': True,
        'verdict': 'intact',
    }
    assert {k: body[k] for k in expected} == expected
    assert body['declared_ends_at']
    # Mesmos nomes do backend Node (camelCase da 001): o script offline e o front os leem.
    assert set(body) == {
        'valid',
        'entries',
        'headHash',
        'head_matches_lot',
        'declared_ends_at',
        'ends_at_mismatch',
        'failure_kind',
        'broken_at_seq',
        'failure_reason',
        'witness_ok',
        'verdict',
    }
