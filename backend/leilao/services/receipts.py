"""Comprovante de arremate (spec 004, D-03, S-07): derivado, sem tabela. O link público é
`/comprovante/<lot_id>.<token>`, com token = HMAC do lote — não é sequencial nem adivinhável sem
o RECEIPT_SECRET."""

import hashlib
import hmac
import re
from typing import TYPE_CHECKING, Any

from leilao.lib.crypto import bidder_pseudonym
from leilao.lib.errors import AppError
from leilao.lib.jsjson import b64url, iso, js_json_parse
from leilao.services.audit import list_audit_entries, verify_lot

if TYPE_CHECKING:
    from leilao.services.context import AppContext

_UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE)
_TOKEN = re.compile(r'[A-Za-z0-9_-]{22}')


def _mac(secret: str, lot_id: str) -> str:
    return b64url(hmac.new(secret.encode(), f'receipt:{lot_id}'.encode(), hashlib.sha256).digest())


def receipt_token(secret: str, lot_id: str) -> str:
    """22 caracteres base64url (~131 bits)."""
    return _mac(secret, lot_id)[:22]


def receipt_id(secret: str, lot_id: str) -> str:
    return f'{lot_id}.{receipt_token(secret, lot_id)}'


def parse_receipt_id(secret: str, receipt: str) -> str | None:
    """Devolve o id do lote se o comprovante for autêntico; `None` caso contrário."""
    dot = receipt.find('.')
    if dot < 0:
        return None
    lot_id, token = receipt[:dot], receipt[dot + 1 :]
    if not _UUID.fullmatch(lot_id) or not _TOKEN.fullmatch(token):
        return None
    expected = receipt_token(secret, lot_id.lower()).encode()
    given = token.encode()
    return lot_id.lower() if len(given) == len(expected) and hmac.compare_digest(given, expected) else None


def receipt_code(secret: str, lot_id: str) -> str:
    """Código curto para exibir: 8 caracteres, maiúsculos, sem 0/O/1/I/L."""
    return re.sub(r'[^A-Z2-9]|[OIL]', '', _mac(secret, lot_id).upper())[:8]


# ---------------------------------------------------------------- conteúdo (S-08)


async def get_receipt(ctx: 'AppContext', receipt: str) -> dict[str, Any]:
    """Comprovante público (FR-017 a FR-022 da 004). Só existe para lote liquidado com vencedor.
    Vencedor (pseudônimo), valor e momento vêm do `lot_settled` assinado; se ele faltar ou a
    trilha não estiver íntegra, a linha do lote supre os dados e o comprovante leva o aviso de
    histórico adulterado. Só a cópia local da imagem."""
    lot_id = parse_receipt_id(ctx.receipt_secret, receipt)
    if not lot_id:
        raise AppError('NOT_FOUND', 'Comprovante não encontrado')
    res = await ctx.db.query(
        """SELECT id, title, image_path, attributes, size, condition, status, leader_user_id, current_price_cents, settled_at
       FROM lots WHERE id = $1""",
        [lot_id],
    )
    lot = res.rows[0] if res.rows else None
    if not lot or lot['status'] != 'settled' or not lot['leader_user_id']:
        raise AppError('NOT_FOUND', 'Comprovante não encontrado')

    verdict = await verify_lot(ctx.db, ctx.signer, ctx.witness, ctx.pseudonym_secret, lot_id)
    settled = [e for e in await list_audit_entries(ctx.db, lot_id) if e['event_type'] == 'lot_settled']
    content: dict[str, Any] = {
        'winner': bidder_pseudonym(ctx.pseudonym_secret, lot['leader_user_id'], lot_id),
        'final_price_cents': lot['current_price_cents'],
        'settled_at': iso(lot['settled_at']),
    }
    if settled and verdict['verdict'] == 'intact':
        p = js_json_parse(settled[-1]['payload_canonical'])
        content = {
            'winner': p.get('winner'),
            'final_price_cents': p.get('final_price_cents'),
            'settled_at': p.get('at'),
        }

    return {
        'receipt_id': receipt_id(ctx.receipt_secret, lot_id),
        'code': receipt_code(ctx.receipt_secret, lot_id),
        'lot': {
            'id': lot_id,
            'number': lot_id[:8].upper(),
            'title': lot['title'],
            'image_url': f'/images/{lot["image_path"]}' if lot['image_path'] else None,
            'attributes': lot['attributes'],
            'size': lot['size'],
            'condition': lot['condition'],
        },
        **content,
        'verdict': {
            'verdict': verdict['verdict'],
            'failure_kind': verdict['failure_kind'],
            'broken_at_seq': verdict['broken_at_seq'],
        },
        'tampered': verdict['verdict'] == 'tampered',
        'audit_url': f'/auditoria/{lot_id}',
    }
