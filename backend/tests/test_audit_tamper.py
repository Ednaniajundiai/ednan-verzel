"""Porte de `audit-tamper.test.ts`: veredito com adulteração direta no banco (FR-003 a FR-005, SC-001 da 004)."""

import json
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest_asyncio

from leilao.lib.jsjson import now_iso
from leilao.services.auction import cancel_lot, place_bid, settle_lot
from leilao.services.audit import AuditSigner, entry_hash, list_audit_entries, verify_lot
from leilao.services.context import AppContext, LotRules
from leilao.services.witness import WitnessLog
from tests.helpers import gather, make_auctioneer, make_lot, make_user, reset_db, sleep


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    # Lotes curtos sem prorrogação: o fim natural não passa pela trilha como adulteração.
    ctx.rules = LotRules(extension_window_ms=0, extension_ms=0)
    yield


async def verdict(ctx: AppContext, lot_id: str) -> dict[str, Any]:
    return await verify_lot(ctx.db, ctx.signer, ctx.witness, ctx.pseudonym_secret, lot_id)


def has(actual: dict[str, Any], **expected: Any) -> bool:
    return all(actual.get(k) == v for k, v in expected.items())


async def tamper(ctx: AppContext, sql: str, params: list[Any]) -> None:
    """Adulteração direta no banco: só neste banco de teste, com o gatilho desligado."""
    await ctx.db.query('ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_update')
    try:
        await ctx.db.query(sql, params)
    finally:
        await ctx.db.query('ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_update')


async def lot_with_bids(ctx: AppContext) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Lote com 3 lances, ainda aberto: lot_opened, bid×3."""
    a, b = await gather(make_user(ctx, 100_000), make_user(ctx, 100_000))
    lot_id = await make_lot(ctx)
    await place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=100)
    await place_bid(ctx, user_id=b['id'], lot_id=lot_id, amount_cents=200)
    await place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=300)
    await sleep(20)  # a testemunha é escrita depois do COMMIT
    return lot_id, a, b


async def settled_lot(ctx: AppContext) -> str:
    """Lote encerrado de verdade (fim natural) e liquidado."""
    u = await make_user(ctx, 100_000)
    lot_id = await make_lot(ctx, duration_ms=300)
    await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=500)
    await sleep(350)
    await settle_lot(ctx, lot_id)
    await sleep(20)
    return lot_id


def empty_witness(ctx: AppContext) -> WitnessLog:
    return WitnessLog(Path(tempfile.mkdtemp(prefix='wit-')) / 'w.jsonl', ctx.signer)


async def test_lote_intacto_aberto_e_encerrado_integro(ctx: AppContext) -> None:
    lot_id, _, _ = await lot_with_bids(ctx)
    assert has(await verdict(ctx, lot_id), verdict='intact', failure_kind=None, witness_ok=True)
    assert has(await verdict(ctx, await settled_lot(ctx)), verdict='intact', failure_kind=None)


async def test_update_do_valor_de_um_lance_altered_no_elo_alterado(ctx: AppContext) -> None:
    lot_id, _, _ = await lot_with_bids(ctx)
    await tamper(
        ctx,
        """UPDATE audit_log SET payload_canonical = replace(payload_canonical, '"amount_cents":200', '"amount_cents":20') WHERE lot_id = $1 AND seq = 3""",
        [lot_id],
    )
    assert has(await verdict(ctx, lot_id), verdict='tampered', failure_kind='altered', broken_at_seq=3)


async def test_delete_de_um_lance_do_meio_missing(ctx: AppContext) -> None:
    lot_id, _, _ = await lot_with_bids(ctx)
    await tamper(ctx, 'DELETE FROM audit_log WHERE lot_id = $1 AND seq = 3', [lot_id])
    assert has(await verdict(ctx, lot_id), verdict='tampered', failure_kind='missing', broken_at_seq=4)


async def test_delete_do_ultimo_elo_com_cabeca_reescrita_truncated_pela_testemunha(ctx: AppContext) -> None:
    lot_id, _, _ = await lot_with_bids(ctx)
    entries = await list_audit_entries(ctx.db, lot_id)
    await tamper(ctx, 'DELETE FROM audit_log WHERE lot_id = $1 AND seq = 4', [lot_id])
    await ctx.db.query(
        'UPDATE lots SET audit_head_hash = $2, audit_seq = 3 WHERE id = $1', [lot_id, entries[2]['hash']]
    )
    v = await verdict(ctx, lot_id)
    assert has(v, verdict='tampered', failure_kind='truncated', broken_at_seq=4, witness_ok=False)
    assert v['head_matches_lot'] is True  # só a testemunha fora do banco percebe


async def test_insert_de_elo_forjado_inserted(ctx: AppContext) -> None:
    """Hash certo, assinatura de outra chave."""
    lot_id, _, _ = await lot_with_bids(ctx)
    last = (await list_audit_entries(ctx.db, lot_id))[-1]
    payload = json.dumps(
        {'amount_cents': 999_999, 'at': now_iso(), 'bid_id': 999, 'bidder': 'ffffffffffffffff'}, separators=(',', ':')
    )
    digest = entry_hash(last['hash'], lot_id, 5, 'bid_placed', payload)
    await tamper(
        ctx,
        "INSERT INTO audit_log (lot_id, seq, event_type, payload_canonical, prev_hash, hash, signature) VALUES ($1, 5, 'bid_placed', $2, $3, $4, $5)",
        [lot_id, payload, last['hash'], digest, AuditSigner.ephemeral().sign(digest)],
    )
    assert has(await verdict(ctx, lot_id), verdict='tampered', failure_kind='inserted', broken_at_seq=5)


async def test_encerrado_sem_evento_final_ou_cancelado_sem_lot_cancelled_truncated(ctx: AppContext) -> None:
    """Sem testemunha: a checagem cruzada com o estado do lote percebe."""
    settled = await settled_lot(ctx)
    owner = await make_auctioneer(ctx)
    cancelled = await make_lot(ctx, auctioneer_id=owner['id'])
    await cancel_lot(ctx, auctioneer_id=owner['id'], lot_id=cancelled)
    for lot_id in (settled, cancelled):
        entries = await list_audit_entries(ctx.db, lot_id)
        n = len(entries)
        await tamper(ctx, 'DELETE FROM audit_log WHERE lot_id = $1 AND seq = $2', [lot_id, n])
        await ctx.db.query(
            'UPDATE lots SET audit_head_hash = $2, audit_seq = $3 WHERE id = $1',
            [lot_id, entries[n - 2]['hash'], n - 1],
        )
    ctx.witness = empty_witness(ctx)
    for lot_id in (settled, cancelled):
        assert has(await verdict(ctx, lot_id), verdict='tampered', failure_kind='truncated', witness_ok=None)


async def test_preco_lider_contagem_ou_fim_divergentes_state_mismatch(ctx: AppContext) -> None:
    cases: list[tuple[str, list[str]]] = [
        ('UPDATE lots SET current_price_cents = 1 WHERE id = $1', []),
        ('UPDATE lots SET leader_user_id = $2 WHERE id = $1', ['b']),
        ('UPDATE lots SET bid_count = 7 WHERE id = $1', []),
        ("UPDATE lots SET ends_at = ends_at + interval '1 hour' WHERE id = $1", []),
    ]
    for sql, extra in cases:
        lot_id, _, b = await lot_with_bids(ctx)
        await ctx.db.query(sql, [lot_id, *(b['id'] if x == 'b' else x for x in extra)])
        assert has(await verdict(ctx, lot_id), verdict='tampered', failure_kind='state_mismatch')


async def test_prorrogacao_fim_vigente_devolvido_ao_original_state_mismatch(ctx: AppContext) -> None:
    ctx.rules = LotRules(extension_window_ms=120_000, extension_ms=120_000)
    u = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx, duration_ms=60_000)
    await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100)
    await sleep(20)
    assert has(await verdict(ctx, lot_id), verdict='intact')
    await ctx.db.query('UPDATE lots SET ends_at = original_ends_at WHERE id = $1', [lot_id])
    assert has(await verdict(ctx, lot_id), verdict='tampered', failure_kind='state_mismatch', ends_at_mismatch=True)
