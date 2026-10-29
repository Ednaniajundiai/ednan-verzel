"""Testemunha da trilha fora do banco (spec 004, D-02, S-05).

Depois de cada COMMIT que acrescenta um elo, grava `{lot_id, seq, head_hash, at, sig}`
num arquivo só de acréscimo. Quem apaga o fim da cadeia e reescreve a cabeça no banco
não alcança este arquivo: a verificação percebe que falta o elo testemunhado.
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from leilao.lib.jsjson import js_json_parse, now_iso

if TYPE_CHECKING:
    from leilao.services.audit import AuditSigner

log = logging.getLogger('leilao.witness')


class WitnessEntry(TypedDict):
    lot_id: str
    seq: int
    head_hash: str
    at: str
    sig: str


def _text(value: Any) -> str:
    """Interpolação `${valor}` do JavaScript para os campos da testemunha."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'null'
    return str(value)


def witness_message(w: Any) -> str:
    """Mensagem assinada; o prefixo a separa das assinaturas dos elos (que assinam o hash)."""
    return f'witness|{_text(w.get("lot_id"))}|{_text(w.get("seq"))}|{_text(w.get("head_hash"))}|{_text(w.get("at"))}'


def verify_witness(w: Any, public_key_pem: str) -> bool:
    from leilao.services.audit import verify_signature

    try:
        if not isinstance(w, dict) or not isinstance(w.get('sig'), str):
            return False
        return verify_signature(public_key_pem, w['sig'], witness_message(w).encode())
    except Exception:
        return False


class WitnessLog:
    def __init__(self, file: Path, signer: 'AuditSigner') -> None:
        self.file = Path(file)
        self.signer = signer
        self._index: dict[str, WitnessEntry] = {}
        # Linhas ignoradas na carga (JSON ruim ou assinatura inválida).
        self.invalid_lines = 0

    def load(self) -> None:
        """Carrega o último testemunho por lote. Arquivo ausente = sem testemunha."""
        self._index.clear()
        self.invalid_lines = 0
        try:
            text = self.file.read_text(encoding='utf-8')
        except OSError:
            return
        for line in text.split('\n'):
            if not line.strip():
                continue
            try:
                w = js_json_parse(line)
                if not verify_witness(w, self.signer.public_key_pem):
                    raise ValueError('assinatura inválida')
                self._keep(w)
            except Exception:
                self.invalid_lines += 1
        if self.invalid_lines:
            log.warning('[witness] %s linha(s) inválida(s) ignorada(s) em %s', self.invalid_lines, self.file)

    async def record(self, lot_id: str, seq: int, head_hash: str) -> None:
        base = {'lot_id': lot_id, 'seq': seq, 'head_hash': head_hash, 'at': now_iso()}
        entry: WitnessEntry = {**base, 'sig': self.signer.sign_message(witness_message(base))}  # type: ignore[typeddict-item]
        self.file.parent.mkdir(parents=True, exist_ok=True)
        # Mesma linha do `JSON.stringify` do Node: sem espaços, na ordem dos campos.
        with self.file.open('a', encoding='utf-8') as f:
            f.write(json.dumps(entry, separators=(',', ':'), ensure_ascii=False) + '\n')
        self._keep(entry)

    def get(self, lot_id: str) -> WitnessEntry | None:
        return self._index.get(lot_id)

    def _keep(self, w: WitnessEntry) -> None:
        current = self._index.get(w['lot_id'])
        # Ganchos de commits seguidos podem terminar fora de ordem: vale o maior seq.
        if not current or w['seq'] > current['seq']:
            self._index[w['lot_id']] = w
