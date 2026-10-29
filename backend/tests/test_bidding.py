"""Porte de `bidding.test.ts`: motor de lances sob concorrência (P1, P2)."""

import itertools
import random
from collections.abc import AsyncIterator

import pytest_asyncio

from leilao.services.auction import place_bid
from leilao.services.audit import list_audit_entries, verify_chain
from leilao.services.context import AppContext
from leilao.services.wallet import wallet_summary
from tests.helpers import count_by, expire_lot, gather, lot_row, make_lot, make_user, outcome, reset_db


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    yield


async def test_cs1_50_lances_paralelos_valores_distintos(ctx: AppContext) -> None:
    """CS1: preço final = maior aceito, histórico estritamente crescente."""
    lot_id = await make_lot(ctx, starting_price_cents=100, min_increment_cents=10)
    users = await gather(*(make_user(ctx, 1_000_000) for _ in range(50)))
    # Valores distintos em ordem embaralhada: chegam fora de ordem ao banco.
    amounts = [100 + i * 10 for i in range(len(users))]
    random.shuffle(amounts)

    results = await gather(
        *(outcome(place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=amounts[i])) for i, u in enumerate(users))
    )

    bids = (await ctx.db.query('SELECT amount_cents FROM bids WHERE lot_id = $1 ORDER BY id', [lot_id])).rows
    accepted = results.count('OK')
    assert len(bids) == accepted
    for prev, cur in itertools.pairwise(bids):
        assert cur['amount_cents'] >= prev['amount_cents'] + 10
    lot = await lot_row(ctx, lot_id)
    assert lot['current_price_cents'] == bids[-1]['amount_cents']
    assert lot['bid_count'] == accepted
    # Todo resultado é um aceite ou um "lance baixo" — nenhum erro inesperado (deadlock, 500).
    assert all(r in ('OK', 'BID_TOO_LOW') for r in results)

    chain = verify_chain(await list_audit_entries(ctx.db, lot_id), ctx.signer.public_key_pem)
    assert chain['valid'] is True
    assert chain['entries'] == accepted + 1


async def test_20_lances_paralelos_com_o_mesmo_valor_exatamente_um_aceito(ctx: AppContext) -> None:
    lot_id = await make_lot(ctx, starting_price_cents=500)
    users = await gather(*(make_user(ctx, 10_000) for _ in range(20)))
    results = await gather(*(outcome(place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=500)) for u in users))
    assert count_by(results) == {'OK': 1, 'BID_TOO_LOW': 19}


async def test_cs2_mesmo_usuario_10_lotes_em_paralelo_saldo_para_um(ctx: AppContext) -> None:
    user = await make_user(ctx, 1_000)
    lots = await gather(*(make_lot(ctx, starting_price_cents=600) for _ in range(10)))
    results = await gather(*(outcome(place_bid(ctx, user_id=user['id'], lot_id=lid, amount_cents=600)) for lid in lots))
    assert count_by(results) == {'OK': 1, 'INSUFFICIENT_FUNDS': 9}
    assert await wallet_summary(ctx.db, user['id']) == {
        'balance_cents': 1_000,
        'committed_cents': 600,
        'available_cents': 400,
    }


async def test_rb5_ser_superado_libera_o_saldo_imediatamente(ctx: AppContext) -> None:
    alice = await make_user(ctx, 1_000)
    bob = await make_user(ctx, 5_000)
    lot1 = await make_lot(ctx, starting_price_cents=800)
    lot2 = await make_lot(ctx, starting_price_cents=800)

    await place_bid(ctx, user_id=alice['id'], lot_id=lot1, amount_cents=800)
    assert await outcome(place_bid(ctx, user_id=alice['id'], lot_id=lot2, amount_cents=800)) == 'INSUFFICIENT_FUNDS'

    await place_bid(ctx, user_id=bob['id'], lot_id=lot1, amount_cents=900)
    assert (await wallet_summary(ctx.db, alice['id']))['available_cents'] == 1_000
    assert await outcome(place_bid(ctx, user_id=alice['id'], lot_id=lot2, amount_cents=800)) == 'OK'


async def test_cobrir_o_lance_em_lote_que_ja_liderou_nao_conta_o_valor_antigo_em_dobro(ctx: AppContext) -> None:
    alice = await make_user(ctx, 1_000)
    bob = await make_user(ctx, 5_000)
    lot = await make_lot(ctx, starting_price_cents=600, min_increment_cents=100)
    await place_bid(ctx, user_id=alice['id'], lot_id=lot, amount_cents=600)
    await place_bid(ctx, user_id=bob['id'], lot_id=lot, amount_cents=700)
    # Alice já não lidera; 1000 de saldo cobre 800 sem considerar os 600 antigos.
    assert await outcome(place_bid(ctx, user_id=alice['id'], lot_id=lot, amount_cents=800)) == 'OK'


async def test_rb2_primeiro_lance_e_seguintes(ctx: AppContext) -> None:
    """RB2: primeiro lance ≥ preço inicial; seguintes ≥ atual + incremento."""
    a, b = await gather(make_user(ctx, 10_000), make_user(ctx, 10_000))
    lot_id = await make_lot(ctx, starting_price_cents=1_000, min_increment_cents=100)
    assert await outcome(place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=999)) == 'BID_TOO_LOW'
    assert await outcome(place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=1_000)) == 'OK'
    assert await outcome(place_bid(ctx, user_id=b['id'], lot_id=lot_id, amount_cents=1_099)) == 'BID_TOO_LOW'
    assert await outcome(place_bid(ctx, user_id=b['id'], lot_id=lot_id, amount_cents=1_100)) == 'OK'


async def test_rb3_lider_nao_pode_cobrir_o_proprio_lance(ctx: AppContext) -> None:
    a = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx)
    await place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=100)
    assert await outcome(place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=500)) == 'ALREADY_LEADING'


async def test_cs4_lance_em_lote_vencido_e_rejeitado(ctx: AppContext) -> None:
    a = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx)
    await expire_lot(ctx, lot_id)
    assert await outcome(place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=100)) == 'LOT_ENDED'


async def test_rb6_mesma_idempotency_key_em_paralelo_um_unico_lance(ctx: AppContext) -> None:
    a = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx)
    results = await gather(
        *(place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=100, idempotency_key='k-1') for _ in range(5))
    )
    assert len({r.bid_id for r in results}) == 1
    assert len([r for r in results if not r.replayed]) == 1
    assert (await lot_row(ctx, lot_id))['bid_count'] == 1
