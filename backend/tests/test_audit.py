"""Porte de `audit.test.ts`: cadeia de auditoria (P4), privacidade (P5) e prorrogação na trilha (003)."""

import json
from collections.abc import AsyncIterator
from datetime import datetime

import psycopg
import pytest
import pytest_asyncio

from leilao.services.auction import get_lot, place_bid, settle_lot
from leilao.services.audit import AuditSigner, declared_ends_at, list_audit_entries, verify_chain, verify_lot_trail
from leilao.services.context import AppContext, LotRules
from tests.helpers import expire_lot, gather, make_lot, make_user, reset_db


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    ctx.rules = LotRules()
    yield


async def lot_with_history(ctx: AppContext) -> tuple[str, dict[str, str], dict[str, str]]:
    a, b = await gather(make_user(ctx, 10_000), make_user(ctx, 10_000))
    lot_id = await make_lot(ctx)
    await place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=100)
    await place_bid(ctx, user_id=b['id'], lot_id=lot_id, amount_cents=200)
    await expire_lot(ctx, lot_id)
    await settle_lot(ctx, lot_id)
    return lot_id, a, b  # type: ignore[return-value]


async def test_abertura_lances_e_liquidacao_formam_uma_cadeia_valida(ctx: AppContext) -> None:
    lot_id, _, _ = await lot_with_history(ctx)
    entries = await list_audit_entries(ctx.db, lot_id)
    assert [e['event_type'] for e in entries] == ['lot_opened', 'bid_placed', 'bid_placed', 'lot_settled']
    chain = verify_chain(entries, ctx.signer.public_key_pem)
    assert chain['valid'] is True and chain['entries'] == 4


async def test_cs5_alterar_o_valor_de_um_lance_quebra_a_verificacao_naquele_elo(ctx: AppContext) -> None:
    lot_id, _, _ = await lot_with_history(ctx)
    entries = await list_audit_entries(ctx.db, lot_id)
    entries[1]['payload_canonical'] = entries[1]['payload_canonical'].replace('"amount_cents":100', '"amount_cents":1')
    chain = verify_chain(entries, ctx.signer.public_key_pem)
    assert chain['valid'] is False and chain['brokenAtSeq'] == 2


async def test_cs5_recalcular_o_hash_sem_a_chave_privada_falha_na_assinatura(ctx: AppContext) -> None:
    lot_id, _, _ = await lot_with_history(ctx)
    entries = await list_audit_entries(ctx.db, lot_id)
    entries[3]['signature'] = AuditSigner.ephemeral().sign(entries[3]['hash'])
    chain = verify_chain(entries, ctx.signer.public_key_pem)
    assert chain['valid'] is False and chain['brokenAtSeq'] == 4


async def test_remover_um_elo_do_meio_e_detectado(ctx: AppContext) -> None:
    lot_id, _, _ = await lot_with_history(ctx)
    entries = await list_audit_entries(ctx.db, lot_id)
    del entries[1]
    assert verify_chain(entries, ctx.signer.public_key_pem)['valid'] is False


async def test_const_4_3_o_banco_recusa_update_e_delete_na_trilha(ctx: AppContext) -> None:
    lot_id, _, _ = await lot_with_history(ctx)
    with pytest.raises(psycopg.Error, match='append-only'):
        await ctx.db.query("UPDATE audit_log SET payload_canonical = '{}' WHERE lot_id = $1", [lot_id])
    with pytest.raises(psycopg.Error, match='append-only'):
        await ctx.db.query('DELETE FROM audit_log WHERE lot_id = $1', [lot_id])


async def test_cs6_pseudonimo_estavel_no_lote_diferente_entre_lotes_sem_dados_pessoais(ctx: AppContext) -> None:
    lot_id, a, _ = await lot_with_history(ctx)
    other = await make_lot(ctx)
    await place_bid(ctx, user_id=a['id'], lot_id=other, amount_cents=100)

    lot1 = await get_lot(ctx, lot_id)
    lot2 = await get_lot(ctx, other)
    alice_in_lot1 = lot1['bids'][-1]['bidder']  # primeiro lance foi de A
    assert len(alice_in_lot1) == 16 and all(c in '0123456789abcdef' for c in alice_in_lot1)
    assert lot2['bids'][0]['bidder'] != alice_in_lot1

    trail = json.dumps(await list_audit_entries(ctx.db, lot_id)) + json.dumps(lot1)
    assert a['id'] not in trail
    assert a['username'] not in trail


async def test_lot_extended_vem_logo_depois_do_bid_placed_que_o_causou(ctx: AppContext) -> None:
    u = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx, duration_ms=60_000)
    bid = await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100)

    entries = await list_audit_entries(ctx.db, lot_id)
    assert [e['event_type'] for e in entries] == ['lot_opened', 'bid_placed', 'lot_extended']
    opened = json.loads(entries[0]['payload_canonical'])
    extended = json.loads(entries[2]['payload_canonical'])
    assert sorted(extended) == ['at', 'bid_id', 'ends_at_after', 'ends_at_before']
    assert extended['bid_id'] == bid.bid_id
    assert datetime.fromisoformat(extended['ends_at_before']) == datetime.fromisoformat(opened['ends_at'])
    chain = verify_chain(entries, ctx.signer.public_key_pem)
    assert chain['valid'] is True and chain['entries'] == 3

    # O fim declarado na trilha é exatamente o fim vigente (comparado no banco, em µs).
    res = await ctx.db.query(
        'SELECT ends_at = $2::timestamptz AS same FROM lots WHERE id = $1', [lot_id, extended['ends_at_after']]
    )
    assert res.rows[0]['same'] is True


async def test_declared_ends_at_do_lot_opened_ou_da_ultima_prorrogacao(ctx: AppContext) -> None:
    a, b = await gather(make_user(ctx, 10_000), make_user(ctx, 10_000))
    plain = await make_lot(ctx)
    plain_entries = await list_audit_entries(ctx.db, plain)
    assert declared_ends_at(plain_entries) == json.loads(plain_entries[0]['payload_canonical'])['ends_at']

    lot_id = await make_lot(ctx, duration_ms=60_000)
    await place_bid(ctx, user_id=a['id'], lot_id=lot_id, amount_cents=100)
    await place_bid(ctx, user_id=b['id'], lot_id=lot_id, amount_cents=200)
    entries = await list_audit_entries(ctx.db, lot_id)
    extensions = [e for e in entries if e['event_type'] == 'lot_extended']
    assert len(extensions) == 2
    assert declared_ends_at(entries) == json.loads(extensions[-1]['payload_canonical'])['ends_at_after']


async def test_sc007_fim_alterado_direto_no_banco_ends_at_mismatch(ctx: AppContext) -> None:
    u = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx, duration_ms=60_000)
    await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100)
    trail = await verify_lot_trail(ctx.db, ctx.signer.public_key_pem, lot_id)
    assert (trail['valid'], trail['head_matches_lot'], trail['ends_at_mismatch']) == (True, True, False)

    await ctx.db.query("UPDATE lots SET ends_at = ends_at + interval '1 hour' WHERE id = $1", [lot_id])
    tampered = await verify_lot_trail(ctx.db, ctx.signer.public_key_pem, lot_id)
    assert (tampered['valid'], tampered['head_matches_lot'], tampered['ends_at_mismatch']) == (True, True, True)
    assert tampered['declared_ends_at']
