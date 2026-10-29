"""Porte de `witness.test.ts`: testemunha fora do banco (FR-005, S-05 da 004)."""

import json
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from leilao.db import Tx, with_tx
from leilao.lib.jsjson import now_iso
from leilao.services.auction import place_bid
from leilao.services.audit import append_audit_event, verify_lot
from leilao.services.context import AppContext
from leilao.services.witness import WitnessLog, verify_witness
from tests.helpers import lot_row, make_lot, make_user, reset_db, sleep

state: dict[str, Path] = {}


@pytest_asyncio.fixture(autouse=True)
async def reset(ctx: AppContext) -> AsyncIterator[None]:
    await reset_db(ctx.db)
    state['file'] = Path(tempfile.mkdtemp(prefix='wit-')) / 'audit-witness.jsonl'
    ctx.witness = WitnessLog(state['file'], ctx.signer)
    ctx.witness.load()
    yield


def lines() -> list[str]:
    file = state['file']
    return [line for line in file.read_text().strip().split('\n') if line] if file.exists() else []


async def test_grava_uma_linha_assinada_por_evento_depois_do_commit(ctx: AppContext) -> None:
    u = await make_user(ctx, 10_000)
    lot_id = await make_lot(ctx)
    await place_bid(ctx, user_id=u['id'], lot_id=lot_id, amount_cents=100)
    await sleep(20)
    rows = [json.loads(line) for line in lines()]
    assert [r['seq'] for r in rows] == [1, 2]
    assert rows[1]['lot_id'] == lot_id and rows[1]['seq'] == 2
    assert rows[1]['head_hash'] == (await lot_row(ctx, lot_id))['audit_head_hash']
    assert verify_witness(rows[1], ctx.signer.public_key_pem) is True
    assert (ctx.witness.get(lot_id) or {}).get('seq') == 2
    # Mesmo formato de linha do `JSON.stringify` do Node: sem espaços, nesta ordem de campos.
    assert list(rows[1]) == ['lot_id', 'seq', 'head_hash', 'at', 'sig']
    assert lines()[1] == json.dumps(rows[1], separators=(',', ':'))


async def test_nao_grava_quando_a_transacao_e_desfeita(ctx: AppContext) -> None:
    lot_id = await make_lot(ctx)
    before = len(lines())

    async def run(tx: Tx) -> None:
        lot = await lot_row(ctx, lot_id)
        await append_audit_event(tx, ctx.signer, lot, 'bid_placed', {'x': 1}, ctx.witness)
        raise RuntimeError('rollback')

    with pytest.raises(RuntimeError, match='rollback'):
        await with_tx(ctx.db, run)
    await sleep(20)
    assert len(lines()) == before
    assert (ctx.witness.get(lot_id) or {}).get('seq') == 1


async def test_recarrega_o_indice_no_boot(ctx: AppContext) -> None:
    lot_id = await make_lot(ctx)
    await sleep(20)
    reloaded = WitnessLog(state['file'], ctx.signer)
    reloaded.load()
    assert reloaded.get(lot_id) == ctx.witness.get(lot_id)


async def test_arquivo_ausente_vira_sem_testemunha_sem_acusar_adulteracao(ctx: AppContext) -> None:
    lot_id = await make_lot(ctx)
    await sleep(20)
    ctx.witness = WitnessLog(state['file'].parent / 'nao-existe.jsonl', ctx.signer)
    ctx.witness.load()
    v = await verify_lot(ctx.db, ctx.signer, ctx.witness, ctx.pseudonym_secret, lot_id)
    assert (v['verdict'], v['witness_ok'], v['witness']) == ('intact', None, None)


async def test_linha_com_assinatura_invalida_e_ignorada_e_contada(ctx: AppContext) -> None:
    lot_id = await make_lot(ctx)
    await sleep(20)
    forged = {'lot_id': lot_id, 'seq': 9, 'head_hash': 'f' * 64, 'at': now_iso(), 'sig': 'AAAA'}
    with state['file'].open('a') as f:
        f.write(json.dumps(forged, separators=(',', ':')) + '\nlixo que não é json\n')
    reloaded = WitnessLog(state['file'], ctx.signer)
    reloaded.load()
    assert (reloaded.get(lot_id) or {}).get('seq') == 1
    assert reloaded.invalid_lines == 2
