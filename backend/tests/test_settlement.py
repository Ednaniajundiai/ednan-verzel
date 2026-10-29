"""Porte de `settlement.test.ts`: liquidação idempotente (P3), crédito ao leiloeiro (002) e
liquidação depois de prorrogação (003)."""

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

from leilao.services.auction import get_lot, place_bid, settle_due_lots, settle_lot
from leilao.services.audit import list_audit_entries, verify_chain
from leilao.services.context import AppContext, LotRules, LotSettledEvent
from leilao.services.wallet import wallet_summary
from tests.helpers import expire_lot, gather, lot_row, make_auctioneer, make_lot, make_user, outcome, reset_db, sleep


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    ctx.events.remove_all_listeners()
    ctx.rules = LotRules()
    yield


async def test_cs3_liquidacao_10x_mais_job_3x_em_paralelo_um_unico_debito(ctx: AppContext) -> None:
    winner = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx)
    await place_bid(ctx, user_id=winner['id'], lot_id=lot_id, amount_cents=2_500)
    await expire_lot(ctx, lot_id)

    events: list[LotSettledEvent] = []
    ctx.events.on('lot:settled', events.append)
    await gather(*(settle_lot(ctx, lot_id) for _ in range(10)), *(settle_due_lots(ctx) for _ in range(3)))

    ledger = await ctx.db.query(
        "SELECT amount_cents FROM ledger_entries WHERE lot_id = $1 AND kind = 'settlement_debit'", [lot_id]
    )
    assert ledger.rows == [{'amount_cents': -2_500}]
    assert len(events) == 1
    assert await wallet_summary(ctx.db, winner['id']) == {
        'balance_cents': 7_500,
        'committed_cents': 0,
        'available_cents': 7_500,
    }
    assert (await lot_row(ctx, lot_id))['status'] == 'settled'


async def test_lote_sem_lances_vira_unsold_e_nao_move_dinheiro(ctx: AppContext) -> None:
    lot_id = await make_lot(ctx)
    await expire_lot(ctx, lot_id)
    assert await settle_due_lots(ctx) == 1
    assert (await lot_row(ctx, lot_id))['status'] == 'unsold'
    assert (await ctx.db.query('SELECT 1 FROM ledger_entries WHERE lot_id = $1', [lot_id])).rowcount == 0


async def test_nao_liquida_antes_do_horario(ctx: AppContext) -> None:
    lot_id = await make_lot(ctx, duration_ms=60_000)
    assert await settle_lot(ctx, lot_id) is None
    assert await settle_due_lots(ctx) == 0
    assert (await lot_row(ctx, lot_id))['status'] == 'open'


async def test_rb9_leitura_de_lote_vencido_o_liquida_na_hora(ctx: AppContext) -> None:
    u = await make_user(ctx, 1_000)
    lot_id = await make_lot(ctx)
    await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=300)
    await expire_lot(ctx, lot_id)
    lot = await get_lot(ctx, lot_id)
    assert lot['status'] == 'settled'
    assert lot['leader'] == lot['bids'][0]['bidder']


async def test_corrida_lance_x_encerramento_todo_lance_aceito_e_anterior_ao_fim(ctx: AppContext) -> None:
    """CS4 da 001, sem prorrogação (janela 0): com ela o lote não fecharia enquanto houvesse lances."""
    ctx.rules = LotRules(extension_window_ms=0, extension_ms=0)
    users = await gather(*(make_user(ctx, 1_000_000) for _ in range(8)))
    lot_id = await make_lot(ctx, duration_ms=400, starting_price_cents=100, min_increment_cents=1)

    # Martela o lote até ele fechar, enquanto o job de liquidação roda em paralelo.
    stop = False

    async def settler() -> None:
        while not stop:
            await settle_due_lots(ctx)
            await sleep(5)

    async def hammer(u: dict[str, Any], i: int) -> None:
        n = 0
        while True:
            r = await outcome(place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100 + n * 100 + i))
            if r == 'LOT_ENDED':
                return
            n += 1

    settling = asyncio.create_task(settler())
    await gather(*(hammer(u, i) for i, u in enumerate(users)))
    stop = True
    await settling
    await settle_lot(ctx, lot_id)

    lot = await lot_row(ctx, lot_id)
    # Comparação no banco, em microssegundos.
    late = await ctx.db.query(
        'SELECT 1 FROM bids b JOIN lots l ON l.id = b.lot_id WHERE b.lot_id = $1 AND b.created_at >= l.ends_at',
        [lot_id],
    )
    assert late.rowcount == 0
    last = (
        await ctx.db.query(
            'SELECT user_id, amount_cents FROM bids WHERE lot_id = $1 ORDER BY id DESC LIMIT 1', [lot_id]
        )
    ).rows[0]
    assert lot['status'] == 'settled'
    assert lot['current_price_cents'] == last['amount_cents']
    # Spec 002: o lote também gera o crédito do leiloeiro; aqui interessa o débito do vencedor.
    debit = await ctx.db.query(
        "SELECT user_id, amount_cents FROM ledger_entries WHERE lot_id = $1 AND kind = 'settlement_debit'", [lot_id]
    )
    assert debit.rows == [{'user_id': last['user_id'], 'amount_cents': -last['amount_cents']}]
    assert verify_chain(await list_audit_entries(ctx.db, lot_id), ctx.signer.public_key_pem)['valid'] is True


# ---------------------------------------------------------------- crédito ao leiloeiro (spec 002, US6)


async def sold_lot(ctx: AppContext, price_cents: int) -> tuple[dict[str, Any], dict[str, Any], str]:
    owner = await make_auctioneer(ctx)
    winner = await make_user(ctx, 100_000)
    lot_id = await make_lot(ctx, auctioneer_id=owner['id'])
    await place_bid(ctx, user_id=winner['id'], lot_id=lot_id, amount_cents=price_cents)
    await expire_lot(ctx, lot_id)
    return owner, winner, lot_id


async def entries(ctx: AppContext, lot_id: str) -> list[dict[str, Any]]:
    res = await ctx.db.query(
        'SELECT user_id, kind, amount_cents FROM ledger_entries WHERE lot_id = $1 ORDER BY kind', [lot_id]
    )
    return res.rows


async def test_fr019_vencedor_debitado_e_leiloeiro_creditado(ctx: AppContext) -> None:
    owner, winner, lot_id = await sold_lot(ctx, 4_200)
    await settle_lot(ctx, lot_id)
    assert await entries(ctx, lot_id) == [
        {'user_id': owner['id'], 'kind': 'settlement_credit', 'amount_cents': 4_200},
        {'user_id': winner['id'], 'kind': 'settlement_debit', 'amount_cents': -4_200},
    ]
    assert (await wallet_summary(ctx.db, owner['id']))['balance_cents'] == 4_200
    assert (await wallet_summary(ctx.db, winner['id']))['balance_cents'] == 100_000 - 4_200


async def test_fr020_20_liquidacoes_paralelas_mais_job_1_debito_e_1_credito(ctx: AppContext) -> None:
    owner, _winner, lot_id = await sold_lot(ctx, 7_700)
    await gather(*(settle_lot(ctx, lot_id) for _ in range(20)), settle_due_lots(ctx), settle_due_lots(ctx))
    rows = await entries(ctx, lot_id)
    assert [r['kind'] for r in rows] == ['settlement_credit', 'settlement_debit']
    assert (await wallet_summary(ctx.db, owner['id']))['balance_cents'] == 7_700


async def test_fr019_lote_sem_lances_nao_gera_lancamento(ctx: AppContext) -> None:
    owner = await make_auctioneer(ctx)
    lot_id = await make_lot(ctx, auctioneer_id=owner['id'])
    await expire_lot(ctx, lot_id)
    await settle_lot(ctx, lot_id)
    assert (await lot_row(ctx, lot_id))['status'] == 'unsold'
    assert await entries(ctx, lot_id) == []
    assert (await wallet_summary(ctx.db, owner['id']))['balance_cents'] == 0


async def test_fr019_falha_no_credito_desfaz_tudo_retomada_conclui(ctx: AppContext) -> None:
    owner, winner, lot_id = await sold_lot(ctx, 3_000)
    await ctx.db.query('DELETE FROM wallets WHERE user_id = $1', [owner['id']])

    with pytest.raises(Exception):  # noqa: B017 (qualquer falha serve: o ponto é desfazer tudo)
        await settle_lot(ctx, lot_id)
    assert await entries(ctx, lot_id) == []
    assert (await lot_row(ctx, lot_id))['status'] == 'open'
    assert (await wallet_summary(ctx.db, winner['id']))['balance_cents'] == 100_000

    await ctx.db.query('INSERT INTO wallets (user_id) VALUES ($1)', [owner['id']])
    await settle_lot(ctx, lot_id)
    assert [r['kind'] for r in await entries(ctx, lot_id)] == ['settlement_credit', 'settlement_debit']
    assert (await lot_row(ctx, lot_id))['status'] == 'settled'


# ---------------------------------------------------------------- depois de prorrogação (spec 003)


async def test_job_e_leitura_nao_liquidam_antes_do_novo_fim(ctx: AppContext) -> None:
    ctx.rules = LotRules(extension_window_ms=300, extension_ms=600)
    u = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx, duration_ms=200)
    await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100)

    await sleep(300)  # passou do fim original, não do prorrogado
    assert await settle_due_lots(ctx) == 0
    assert (await get_lot(ctx, lot_id))['status'] == 'open'

    await sleep(450)
    assert (await get_lot(ctx, lot_id))['status'] == 'settled'
    assert await settle_due_lots(ctx) == 0


async def test_corrida_com_janela_curta_lances_prorrogam_e_depois_o_lote_fecha(ctx: AppContext) -> None:
    ctx.rules = LotRules(extension_window_ms=100, extension_ms=100)
    users = await gather(*(make_user(ctx, 1_000_000) for _ in range(6)))
    lot_id = await make_lot(ctx, duration_ms=300, starting_price_cents=100, min_increment_cents=1)
    deadline = time.monotonic() + 1.5

    async def hammer(u: dict[str, Any], i: int) -> list[str]:
        mine: list[str] = []
        n = 0
        while time.monotonic() < deadline:
            r = await outcome(place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100 + n * 100 + i))
            mine.append(r)
            if r == 'LOT_ENDED':
                break
            n += 1
        return mine

    results = await gather(*(hammer(u, i) for i, u in enumerate(users)))
    assert all(r in ('OK', 'BID_TOO_LOW', 'ALREADY_LEADING', 'LOT_ENDED') for rs in results for r in rs)
    await sleep(250)
    await settle_lot(ctx, lot_id)

    late = await ctx.db.query(
        'SELECT 1 FROM bids b JOIN lots l ON l.id = b.lot_id WHERE b.lot_id = $1 AND b.created_at >= l.ends_at',
        [lot_id],
    )
    assert late.rowcount == 0
    lot = await lot_row(ctx, lot_id)
    last = (
        await ctx.db.query(
            'SELECT user_id, amount_cents FROM bids WHERE lot_id = $1 ORDER BY id DESC LIMIT 1', [lot_id]
        )
    ).rows[0]
    assert lot['status'] == 'settled'
    assert lot['current_price_cents'] == last['amount_cents']
    assert verify_chain(await list_audit_entries(ctx.db, lot_id), ctx.signer.public_key_pem)['valid'] is True
