import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, TypedDict

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from leilao.db import Db, Queryable, Tx
from leilao.lib.crypto import bidder_pseudonym, canonical_json, sha256_hex
from leilao.lib.errors import AppError
from leilao.lib.jsjson import b64, js_json_parse, node_b64decode
from leilao.services.witness import WitnessEntry, WitnessLog, verify_witness

GENESIS_HASH = '0' * 64

AuditEventType = Literal['lot_opened', 'bid_placed', 'lot_extended', 'lot_settled', 'lot_unsold', 'lot_cancelled']
FailureKind = Literal['altered', 'inserted', 'missing', 'truncated', 'state_mismatch']


class AuditEntry(TypedDict):
    lot_id: str
    seq: int
    event_type: str
    payload_canonical: str
    prev_hash: str
    hash: str
    signature: str


class AuditSigner:
    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._key = private_key
        self.public_key_pem = (
            private_key.public_key()
            .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            .decode('ascii')
        )

    @staticmethod
    def _from_pem(pem: bytes) -> 'AuditSigner':
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError('a chave da auditoria precisa ser Ed25519')
        return AuditSigner(key)

    @staticmethod
    def load(pem: str | None, storage_dir: Path) -> 'AuditSigner':
        """Usa a chave do ambiente; em dev, gera uma vez e persiste para a cadeia sobreviver a restarts."""
        if pem:
            return AuditSigner._from_pem(pem.encode())
        file = Path(storage_dir) / 'audit-ed25519.pem'
        if not file.exists():
            storage_dir.mkdir(parents=True, exist_ok=True)
            data = Ed25519PrivateKey.generate().private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
            fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
        return AuditSigner._from_pem(file.read_bytes())

    @staticmethod
    def ephemeral() -> 'AuditSigner':
        return AuditSigner(Ed25519PrivateKey.generate())

    def private_key_pem(self) -> str:
        return self._key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode('ascii')

    def sign(self, hash_hex: str) -> str:
        return b64(self._key.sign(bytes.fromhex(hash_hex)))

    def sign_message(self, text: str) -> str:
        """Assina um texto (usado pela testemunha, com prefixo próprio)."""
        return b64(self._key.sign(text.encode('utf-8')))


@lru_cache(maxsize=16)
def _public_key(pem: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem.encode())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError('chave pública não é Ed25519')
    return key


def verify_signature(public_key_pem: str, signature_b64: str, data: bytes) -> bool:
    key = _public_key(public_key_pem)
    try:
        key.verify(node_b64decode(signature_b64), data)
        return True
    except (InvalidSignature, ValueError):
        return False


def entry_hash(prev_hash: str, lot_id: str, seq: int, event_type: str, payload_canonical: str) -> str:
    return sha256_hex(f'{prev_hash}|{lot_id}|{seq}|{event_type}|{payload_canonical}')


async def append_audit_event(
    tx: Tx,
    signer: AuditSigner,
    lot: dict[str, Any],
    event_type: AuditEventType,
    payload: dict[str, Any],
    witness: WitnessLog | None = None,
) -> AuditEntry:
    """Anexa um evento à cadeia do lote. Pré-condição: o chamador detém o lock (FOR UPDATE)
    da linha do lote — é isso que serializa a cadeia (plan P4 da 001)."""
    seq = lot['audit_seq'] + 1
    payload_canonical = canonical_json(payload)
    digest = entry_hash(lot['audit_head_hash'], lot['id'], seq, event_type, payload_canonical)
    entry: AuditEntry = {
        'lot_id': lot['id'],
        'seq': seq,
        'event_type': event_type,
        'payload_canonical': payload_canonical,
        'prev_hash': lot['audit_head_hash'],
        'hash': digest,
        'signature': signer.sign(digest),
    }
    await tx.query(
        """INSERT INTO audit_log (lot_id, seq, event_type, payload_canonical, prev_hash, hash, signature)
     VALUES ($1, $2, $3, $4, $5, $6, $7)""",
        [
            entry['lot_id'],
            entry['seq'],
            entry['event_type'],
            entry['payload_canonical'],
            entry['prev_hash'],
            entry['hash'],
            entry['signature'],
        ],
    )
    await tx.query('UPDATE lots SET audit_seq = $2, audit_head_hash = $3 WHERE id = $1', [lot['id'], seq, digest])
    lot['audit_seq'] = seq
    lot['audit_head_hash'] = digest
    # Testemunha fora do banco, só depois do COMMIT (spec 004, S-05).
    if witness is not None:
        log = witness
        tx.after_commit(lambda: log.record(entry['lot_id'], seq, digest))
    return entry


async def list_audit_entries(db: Queryable, lot_id: str) -> list[AuditEntry]:
    res = await db.query(
        """SELECT lot_id, seq, event_type, payload_canonical, prev_hash, hash, signature
       FROM audit_log WHERE lot_id = $1 ORDER BY seq""",
        [lot_id],
    )
    return res.rows  # type: ignore[return-value]


def verify_chain(entries: list[AuditEntry], public_key_pem: str) -> dict[str, Any]:
    """Verificação pura (sem banco): qualquer terceiro pode rodá-la com a trilha pública e a
    chave pública (RB11). Usada pela API e por `scripts/verify_audit.py`.

    Mesmos campos do Node: `{valid, entries, headHash}` ou `{valid, entries, brokenAtSeq, reason}`.
    """
    _public_key(public_key_pem)
    prev = GENESIS_HASH
    for i, e in enumerate(entries):

        def fail(reason: str, e: AuditEntry = e) -> dict[str, Any]:
            return {'valid': False, 'entries': len(entries), 'brokenAtSeq': e['seq'], 'reason': reason}

        if e['seq'] != i + 1:
            return fail(f'sequência esperada {i + 1}, encontrada {e["seq"]}')
        if e['prev_hash'] != prev:
            return fail('prev_hash não aponta para o elo anterior')
        if entry_hash(e['prev_hash'], e['lot_id'], e['seq'], e['event_type'], e['payload_canonical']) != e['hash']:
            return fail('hash não confere com o conteúdo')
        if not verify_signature(public_key_pem, e['signature'], bytes.fromhex(e['hash'])):
            return fail('assinatura Ed25519 inválida')
        prev = e['hash']
    return {'valid': True, 'entries': len(entries), 'headHash': prev}


def declared_ends_at(entries: list[AuditEntry]) -> str | None:
    """Fim do lote declarado pela trilha (spec 003, FR-008): o `ends_at` do `lot_opened`, ou o
    `ends_at_after` do último `lot_extended`. Função pura."""
    declared: str | None = None
    for e in entries:
        try:
            payload = js_json_parse(e['payload_canonical'])
        except ValueError:
            continue  # payload ilegível: a verificação da cadeia já acusa
        if not isinstance(payload, dict):
            continue
        if e['event_type'] == 'lot_opened' and isinstance(payload.get('ends_at'), str):
            declared = payload['ends_at']
        if e['event_type'] == 'lot_extended' and isinstance(payload.get('ends_at_after'), str):
            declared = payload['ends_at_after']
    return declared


async def verify_lot_trail(db: Db, public_key_pem: str, lot_id: str) -> dict[str, Any]:
    """Verificação do servidor: a cadeia (`valid`), a cabeça publicada no lote e o fim vigente
    contra o declarado. A comparação do fim é feita no banco, em µs."""
    head = await db.query('SELECT audit_head_hash FROM lots WHERE id = $1', [lot_id])
    if not head.rowcount:
        raise AppError('NOT_FOUND', 'Lote não encontrado')
    entries = await list_audit_entries(db, lot_id)
    result = verify_chain(entries, public_key_pem)
    # A cadeia sozinha não detecta truncamento do fim; a cabeça publicada no lote detecta.
    head_matches = result['valid'] and result['headHash'] == head.rows[0]['audit_head_hash']
    declared = declared_ends_at(entries)
    ends_at_mismatch = True
    if declared:
        try:
            same = await db.query(
                'SELECT ends_at = $2::timestamptz AS same FROM lots WHERE id = $1', [lot_id, declared]
            )
            ends_at_mismatch = not (same.rows and same.rows[0]['same'])
        except Exception:
            ends_at_mismatch = True
    return {
        **result,
        'head_matches_lot': head_matches,
        'declared_ends_at': declared,
        'ends_at_mismatch': ends_at_mismatch,
    }


# ---------------------------------------------------------------- veredito (spec 004)


def _classification(
    kind: FailureKind | None, seq: int | None, reason: str | None, witness_ok: bool | None
) -> dict[str, Any]:
    return {'failure_kind': kind, 'broken_at_seq': seq, 'failure_reason': reason, 'witness_ok': witness_ok}


def classify_trail(entries: list[AuditEntry], public_key_pem: str, witness: WitnessEntry | None) -> dict[str, Any]:
    """Classifica a trilha só com o conteúdo, a chave pública e a testemunha (S-04 da 004).
    Pura: o verificador do navegador implementa a mesma regra com Web Crypto.

    - hash não confere com o conteúdo → `altered`;
    - hash confere, assinatura inválida (elo forjado sem a chave) → `inserted`;
    - salto de `seq` ou `prev_hash` errado, com assinaturas válidas → `missing`;
    - a cadeia não chega ao elo testemunhado → `truncated`.

    `witness_ok`: None = sem testemunha válida; False = a cadeia não contém o elo testemunhado.
    """
    _public_key(public_key_pem)
    prev = GENESIS_HASH
    valid_witness = witness if witness and verify_witness(witness, public_key_pem) else None
    witness_ok: bool | None = None
    if valid_witness:
        n = valid_witness['seq']
        witness_ok = len(entries) >= n and 1 <= n and entries[n - 1]['hash'] == valid_witness['head_hash']

    for i, e in enumerate(entries):
        if entry_hash(e['prev_hash'], e['lot_id'], e['seq'], e['event_type'], e['payload_canonical']) != e['hash']:
            return _classification('altered', e['seq'], 'o conteúdo do evento não confere com o hash', witness_ok)
        try:
            signed = verify_signature(public_key_pem, e['signature'], bytes.fromhex(e['hash']))
        except Exception:
            signed = False
        if not signed:
            return _classification(
                'inserted', e['seq'], 'assinatura inválida: evento que a casa não assinou', witness_ok
            )
        if e['seq'] != i + 1:
            return _classification('missing', e['seq'], f'falta o evento {i + 1} antes deste', witness_ok)
        if e['prev_hash'] != prev:
            return _classification('missing', e['seq'], 'o evento não aponta para o anterior', witness_ok)
        prev = e['hash']
    if valid_witness and len(entries) < valid_witness['seq']:
        return _classification(
            'truncated',
            len(entries) + 1,
            f'a testemunha registrou {valid_witness["seq"]} eventos; a trilha tem {len(entries)}',
            False,
        )
    if valid_witness and not witness_ok:
        return _classification('altered', valid_witness['seq'], 'o evento difere do registrado pela testemunha', False)
    return _classification(None, None, None, witness_ok)


FINAL_EVENT = {'settled': 'lot_settled', 'unsold': 'lot_unsold', 'cancelled': 'lot_cancelled'}


def _cross_check(
    entries: list[AuditEntry], lot: dict[str, Any], pseudonym: Any, trail: dict[str, Any]
) -> tuple[FailureKind, str, int | None] | None:
    """Checagem cruzada da trilha com o estado do lote (D-02 da 004, alternativa A)."""
    if not trail['head_matches_lot']:
        return 'truncated', 'a cabeça publicada no lote não é o último evento da trilha', len(entries) + 1
    last = entries[-1] if entries else None
    expected_final = FINAL_EVENT.get(lot['status'])
    if expected_final and (last['event_type'] if last else None) != expected_final:
        return (
            'truncated',
            f'o lote está {lot["status"]}, mas a trilha não tem o evento {expected_final}',
            len(entries) + 1,
        )
    if not expected_final and last and last['event_type'] in FINAL_EVENT.values():
        return 'state_mismatch', 'a trilha encerra o lote, mas ele está aberto', last['seq']
    bids = [js_json_parse(e['payload_canonical']) for e in entries if e['event_type'] == 'bid_placed']
    last_bid = bids[-1] if bids else None
    if len(bids) != lot['bid_count'] or len(bids) != lot['bids_rows']:
        return 'state_mismatch', 'a contagem de lances do lote difere da trilha', None
    if (last_bid.get('amount_cents') if last_bid else None) != lot['current_price_cents']:
        return 'state_mismatch', 'o preço atual do lote difere do último lance da trilha', None
    leader = pseudonym(lot['leader_user_id']) if lot['leader_user_id'] else None
    if (last_bid.get('bidder') if last_bid else None) != leader:
        return 'state_mismatch', 'o líder do lote difere do último lance da trilha', None
    if trail['ends_at_mismatch']:
        return 'state_mismatch', 'o fim do lote difere do declarado na trilha', None
    return None


async def verify_lot(
    db: Db, signer: AuditSigner, witness_log: WitnessLog, pseudonym_secret: str, lot_id: str
) -> dict[str, Any]:
    """Veredito do servidor (FR-003 a FR-005 da 004): cadeia + testemunha + checagem cruzada com o
    estado do lote. `valid` continua sendo só a cadeia (contrato da 001/003)."""
    trail = await verify_lot_trail(db, signer.public_key_pem, lot_id)
    entries = await list_audit_entries(db, lot_id)
    witness = witness_log.get(lot_id)
    classification = classify_trail(entries, signer.public_key_pem, witness)
    if not classification['failure_kind']:
        res = await db.query(
            """SELECT status, current_price_cents, leader_user_id, bid_count,
              (SELECT count(*)::int FROM bids WHERE lot_id = l.id) AS bids_rows
         FROM lots l WHERE id = $1""",
            [lot_id],
        )
        mismatch = _cross_check(entries, res.rows[0], lambda u: bidder_pseudonym(pseudonym_secret, u, lot_id), trail)
        if mismatch:
            kind, reason, seq = mismatch
            classification = {**classification, 'failure_kind': kind, 'broken_at_seq': seq, 'failure_reason': reason}
    return {
        **trail,
        **classification,
        'witness': witness,
        'verdict': 'tampered' if classification['failure_kind'] else 'intact',
    }
