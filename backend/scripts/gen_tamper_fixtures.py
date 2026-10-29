"""Gera os casos de adulteração usados pelos DOIS verificadores (S-02 da 004): o do servidor
(Python, `cryptography`) e o do navegador (Web Crypto). As cadeias são montadas em memória, com
uma chave efêmera — nada toca o banco (Const. 4.3).

    uv run python -m scripts.gen_tamper_fixtures
"""

import json
from pathlib import Path
from typing import Any

from leilao.config import ROOT
from leilao.lib.crypto import canonical_json
from leilao.services.audit import GENESIS_HASH, AuditEntry, AuditSigner, entry_hash
from leilao.services.witness import WitnessEntry, witness_message

LOT = '5b1c7e2a-9d4f-4c3e-8a6b-1f2e3d4c5b6a'
OUT = ROOT.parent / 'frontend' / 'src' / 'audit' / '__fixtures__' / 'tamper-cases.json'


def chain(signer: AuditSigner, events: list[tuple[str, dict[str, Any]]]) -> list[AuditEntry]:
    prev = GENESIS_HASH
    entries: list[AuditEntry] = []
    for i, (event_type, payload) in enumerate(events):
        payload_canonical = canonical_json(payload)
        digest = entry_hash(prev, LOT, i + 1, event_type, payload_canonical)
        entries.append(
            {
                'lot_id': LOT,
                'seq': i + 1,
                'event_type': event_type,
                'payload_canonical': payload_canonical,
                'prev_hash': prev,
                'hash': digest,
                'signature': signer.sign(digest),
            }
        )
        prev = digest
    return entries


def witness_for(entries: list[AuditEntry], seq: int, by: AuditSigner) -> WitnessEntry:
    base = {'lot_id': LOT, 'seq': seq, 'head_hash': entries[seq - 1]['hash'], 'at': '2026-10-28T20:10:00.000Z'}
    return {**base, 'sig': by.sign_message(witness_message(base))}  # type: ignore[typeddict-item]


def build_cases() -> dict[str, Any]:
    signer = AuditSigner.ephemeral()
    forger = AuditSigner.ephemeral()
    intact = chain(
        signer,
        [
            (
                'lot_opened',
                {
                    'title': 'Camisa Flamengo 2019',
                    'starting_price_cents': 10000,
                    'min_increment_cents': 1000,
                    'starts_at': '2026-10-28T20:00:00.000Z',
                    'ends_at': '2026-10-28T20:10:00.000Z',
                },
            ),
            (
                'bid_placed',
                {'bid_id': 1, 'bidder': 'a1b2c3d4e5f60718', 'amount_cents': 10000, 'at': '2026-10-28T20:01:00.000Z'},
            ),
            (
                'bid_placed',
                {'bid_id': 2, 'bidder': '0f1e2d3c4b5a6978', 'amount_cents': 11000, 'at': '2026-10-28T20:02:00.000Z'},
            ),
            (
                'lot_extended',
                {
                    'bid_id': 2,
                    'ends_at_before': '2026-10-28T20:10:00.000000Z',
                    'ends_at_after': '2026-10-28T20:12:00.000000Z',
                    'at': '2026-10-28T20:02:00.000Z',
                },
            ),
            (
                'lot_settled',
                {
                    'winner': '0f1e2d3c4b5a6978',
                    'final_price_cents': 11000,
                    'bid_count': 2,
                    'at': '2026-10-28T20:12:00.000Z',
                },
            ),
        ],
    )

    def copy() -> list[AuditEntry]:
        return [dict(e) for e in intact]  # type: ignore[misc]

    altered = copy()
    altered[2]['payload_canonical'] = altered[2]['payload_canonical'].replace(
        '"amount_cents":11000', '"amount_cents":1100'
    )

    missing_middle = [e for e in copy() if e['seq'] != 2]

    truncated_end = copy()[:4]

    inserted = copy()
    last = inserted[-1]
    payload_canonical = canonical_json(
        {'bid_id': 99, 'bidder': 'ffffffffffffffff', 'amount_cents': 99999, 'at': '2026-10-28T20:13:00.000Z'}
    )
    digest = entry_hash(last['hash'], LOT, 6, 'bid_placed', payload_canonical)
    inserted.append(
        {
            'lot_id': LOT,
            'seq': 6,
            'event_type': 'bid_placed',
            'payload_canonical': payload_canonical,
            'prev_hash': last['hash'],
            'hash': digest,
            'signature': forger.sign(digest),
        }
    )

    full_witness = witness_for(intact, 5, signer)
    cases = [
        {
            'name': 'intacta, com testemunha',
            'entries': intact,
            'witness': full_witness,
            'expected': {'verdict': 'intact', 'failure_kind': None, 'broken_at_seq': None, 'witness_ok': True},
        },
        {
            'name': 'intacta, sem testemunha',
            'entries': intact,
            'witness': None,
            'expected': {'verdict': 'intact', 'failure_kind': None, 'broken_at_seq': None, 'witness_ok': None},
        },
        {
            'name': 'valor de um lance alterado',
            'entries': altered,
            'witness': full_witness,
            'expected': {'verdict': 'tampered', 'failure_kind': 'altered', 'broken_at_seq': 3},
        },
        {
            'name': 'lance do meio removido',
            'entries': missing_middle,
            'witness': full_witness,
            'expected': {'verdict': 'tampered', 'failure_kind': 'missing', 'broken_at_seq': 3},
        },
        {
            'name': 'último evento removido (a testemunha viu 5)',
            'entries': truncated_end,
            'witness': full_witness,
            'expected': {'verdict': 'tampered', 'failure_kind': 'truncated', 'broken_at_seq': 5, 'witness_ok': False},
        },
        {
            'name': 'lance forjado inserido no fim',
            'entries': inserted,
            'witness': full_witness,
            'expected': {'verdict': 'tampered', 'failure_kind': 'inserted', 'broken_at_seq': 6},
        },
        {
            'name': 'testemunha com assinatura falsa é ignorada',
            'entries': intact,
            'witness': witness_for(intact, 5, forger),
            'expected': {'verdict': 'intact', 'failure_kind': None, 'broken_at_seq': None, 'witness_ok': None},
        },
    ]
    return {'public_key_pem': signer.public_key_pem, 'cases': cases}


def main(out: Path = OUT) -> None:
    data = build_cases()
    out.parent.mkdir(parents=True, exist_ok=True)
    # Mesmo formato do `JSON.stringify(..., null, 2)` do Node.
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'[fixtures] {len(data["cases"])} casos em {out}')


if __name__ == '__main__':
    main()
