"""Porte de `tamper-fixtures.test.ts`: verificador do servidor nos casos compartilhados com o do
navegador (FR-025, SC-007 da 004). O arquivo é gerado por `scripts/gen_tamper_fixtures.py`."""

import json
from typing import Any

import pytest

from leilao.config import ROOT
from leilao.services.audit import classify_trail
from scripts.gen_tamper_fixtures import build_cases

FILE = ROOT.parent / 'frontend' / 'src' / 'audit' / '__fixtures__' / 'tamper-cases.json'
SHARED = json.loads(FILE.read_text(encoding='utf-8'))


def check(public_key_pem: str, case: dict[str, Any]) -> None:
    r = classify_trail(case['entries'], public_key_pem, case['witness'])
    expected = dict(case['expected'])
    verdict = expected.pop('verdict')
    assert ('tampered' if r['failure_kind'] else 'intact') == verdict
    for key, value in expected.items():
        assert r[key] == value, key


@pytest.mark.parametrize('case', SHARED['cases'], ids=lambda c: c['name'])
def test_casos_do_arquivo_compartilhado(case: dict[str, Any]) -> None:
    check(SHARED['public_key_pem'], case)


def test_o_gerador_produz_casos_que_o_servidor_classifica_como_esperado() -> None:
    fresh = build_cases()
    assert [c['name'] for c in fresh['cases']] == [c['name'] for c in SHARED['cases']]
    for case in fresh['cases']:
        check(fresh['public_key_pem'], case)
