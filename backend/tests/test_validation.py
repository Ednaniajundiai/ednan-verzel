"""Validação com as mensagens do Zod (spec 005, T008): tabela gerada com o Zod real do backend Node
(`fixtures/zod-cases.json`), mesma entrada → mesmas `issues` (ou mesma saída)."""

import json
from typing import Any

import pytest

from leilao.http import schemas
from leilao.lib import validation as z
from leilao.lib.errors import AppError
from leilao.services.auction import lot_input_schema
from tests.helpers import FIXTURES

CASES = json.loads((FIXTURES / 'zod-cases.json').read_text(encoding='utf-8'))
U = '__undefined__'

OBJECTS: dict[str, z.Schema] = {
    'register': schemas.register,
    'login': schemas.login,
    'deposit': schemas.deposit,
    'bid': schemas.bid,
    'catalogQuery': schemas.catalog_query,
    'lot': lot_input_schema,
}
VALUES: dict[str, z.Rule] = {'idempotencyKey': schemas.idempotency_key, 'teamId': schemas.team_id, 'uuid': schemas.uuid}


def _run(case: dict[str, Any]) -> Any:
    value = z.UNDEFINED if case['input'] == U else case['input']
    if case['schema'] in OBJECTS:
        return OBJECTS[case['schema']].parse(value)
    out = z.parse_value(VALUES[case['schema']], value)
    return U if out is z.UNDEFINED else out


@pytest.mark.parametrize(
    'case', CASES, ids=lambda c: f'{c["schema"]}:{json.dumps(c["input"], ensure_ascii=False)[:50]}'
)
def test_mesmo_resultado_do_zod(case: dict[str, Any]) -> None:
    if case['ok']:
        assert _run(case) == case['output']
    else:
        with pytest.raises(AppError) as err:
            _run(case)
        assert err.value.code == 'VALIDATION'
        assert err.value.message == 'Entrada inválida'
        assert err.value.details == {'issues': case['issues']}


def test_centavos_viram_int() -> None:
    out = schemas.deposit.parse({'amount_cents': 100.0})
    assert out == {'amount_cents': 100}
    assert type(out['amount_cents']) is int
