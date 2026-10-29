"""Porte de `receipt-token.test.ts`: id do comprovante (FR-019, S-07 da 004)."""

import re

from leilao.lib.crypto import bidder_pseudonym
from leilao.services.receipts import parse_receipt_id, receipt_code, receipt_id, receipt_token

LOT = '3aa9af76-a57e-4748-8c30-a1993559d0d5'
OTHER = '3f3b0e7e-62a3-4443-8d08-84b731d791f5'


def test_token_deterministico_por_lote_muda_com_o_segredo_22_caracteres_base64url() -> None:
    t = receipt_token('segredo', LOT)
    assert re.fullmatch(r'[A-Za-z0-9_-]{22}', t)
    assert receipt_token('segredo', LOT) == t
    assert receipt_token('outro', LOT) != t
    assert receipt_token('segredo', OTHER) != t


def test_id_lote_ponto_token_malformado_ou_trocado_e_recusado() -> None:
    rid = receipt_id('segredo', LOT)
    assert rid == f'{LOT}.{receipt_token("segredo", LOT)}'
    assert parse_receipt_id('segredo', rid) == LOT
    assert parse_receipt_id('segredo', f'{LOT.upper()}.{receipt_token("segredo", LOT)}') == LOT

    t = receipt_token('segredo', LOT)
    flipped = f'{LOT}.{t[:-1]}{"B" if t.endswith("A") else "A"}'
    for bad in (flipped, LOT, f'{LOT}.', f'nao-e-uuid.{t}', f'{LOT}.{t}x', f'{OTHER}.{t}', '', '..'):
        assert parse_receipt_id('segredo', bad) is None


def test_codigo_exibido_8_caracteres_maiusculos_sem_ambiguos() -> None:
    code = receipt_code('segredo', LOT)
    assert re.fullmatch(r'[A-Z2-9]{8}', code)
    assert not re.search(r'[01OIL]', code)


def test_mesmos_valores_do_backend_node() -> None:
    """Valores calculados pelo backend Node com o mesmo segredo: links e pseudônimos antigos continuam valendo."""
    assert receipt_token('segredo', LOT) == 'kH0uFhB4hmpwMwbv9InhIg'
    assert receipt_code('segredo', LOT) == 'KHUFHB4H'
    assert bidder_pseudonym('test-pseudonym-secret', 'u1', 'l1') == '8026042db6232e7f'
