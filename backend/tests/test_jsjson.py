"""Compatibilidade byte a byte com o Node (spec 005, T006): `canonicalJson` e `toISOString`,
contra valores gerados pelo próprio backend Node (`fixtures/node-compat.json`)."""

import json

import pytest

from leilao.lib.jsjson import canonical_json, iso, js_length, js_trim, node_b64decode
from leilao.services.context import AppContext
from tests.helpers import FIXTURES

COMPAT = json.loads((FIXTURES / 'node-compat.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', COMPAT['canonical'], ids=lambda c: c['input'][:40])
def test_canonical_json_igual_ao_do_node(case: dict[str, str]) -> None:
    assert canonical_json(json.loads(case['input'])) == case['output']


@pytest.mark.parametrize('case', COMPAT['iso'], ids=lambda c: c['pg'])
async def test_iso_igual_ao_toISOString_de_um_timestamptz_lido_pelo_pg(ctx: AppContext, case: dict[str, str]) -> None:
    res = await ctx.db.query('SELECT $1::timestamptz AS t', [case['pg']])
    assert iso(res.rows[0]['t']) == case['iso']


def test_utilitarios_do_javascript() -> None:
    assert js_trim(' ﻿ Ana 　\n') == 'Ana'
    assert js_trim('\x1c Ana') == '\x1c Ana'  # o Python removeria; o JavaScript não
    assert js_length('😀') == 2
    assert node_b64decode('AAAA') == b'\x00\x00\x00'
    assert node_b64decode('AA A=A') == b'\x00\x00'  # para no `=`, ignora lixo
    assert node_b64decode('-_8') == node_b64decode('+/8')
