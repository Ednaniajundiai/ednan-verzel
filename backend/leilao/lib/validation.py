"""Validação de entrada com Pydantic v2, reproduzindo os schemas Zod do backend Node (spec 005, D-03).

O front mostra as mensagens de `issues` por campo; por isso cada regra devolve
a mesma mensagem do Zod 4 (padrão em inglês ou a mensagem própria do schema) e
na mesma ordem. Como no Zod, cada campo para na primeira regra que falha.
"""

import math
import re
from collections.abc import Callable, Sequence
from typing import Annotated, Any, Final

from pydantic import BaseModel, ConfigDict, Field, PlainValidator, ValidationError, create_model
from pydantic_core import PydanticCustomError

from leilao.lib.errors import AppError
from leilao.lib.jsjson import js_trim


class _Undefined:
    """`undefined` do JavaScript: campo ausente no JSON."""

    def __repr__(self) -> str:
        return 'undefined'


UNDEFINED: Final = _Undefined()

# Regexes do Zod 4 (`zod/v4/core/regexes`), com `\d` ASCII como no JavaScript.
EMAIL_RE = re.compile(
    r"(?:[A-Za-z0-9_'+\-]+\.)*[A-Za-z0-9_'+\-]*[A-Za-z0-9_+-]@(?:[A-Za-z0-9][A-Za-z0-9\-]*\.)+[A-Za-z]{2,}"
)
UUID_RE = re.compile(
    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}'
    r'|00000000-0000-0000-0000-000000000000|ffffffff-ffff-ffff-ffff-ffffffffffff'
)
_DATE = (
    r'(?:(?:\d\d[2468][048]|\d\d[13579][26]|\d\d0[48]|[02468][048]00|[13579][26]00)-02-29'
    r'|\d{4}-(?:(?:0[13578]|1[02])-(?:0[1-9]|[12]\d|3[01])|(?:0[469]|11)-(?:0[1-9]|[12]\d|30)|(?:02)-(?:0[1-9]|1\d|2[0-8])))'
)
# z.iso.datetime({ offset: true }): segundos obrigatórios, fração livre, `Z` ou `±hh:mm`.
ISO_DATETIME_RE = re.compile(
    rf'{_DATE}T(?:(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|([+-](?:[01]\d|2[0-3]):[0-5]\d)))', re.ASCII
)
MAX_SAFE_INTEGER: Final = 2**53 - 1


class Issue(Exception):
    """Falha de uma checagem. `abort=False` registra a mensagem e segue para a próxima (como no Zod)."""

    def __init__(self, message: str, abort: bool = True) -> None:
        super().__init__(message)
        self.message = message
        self.abort = abort


class Issues(Exception):
    def __init__(self, messages: list[str]) -> None:
        super().__init__('; '.join(messages))
        self.messages = messages


def _received(value: Any) -> str:
    """Nome do tipo recebido, como o `parsedType` do Zod."""
    if value is UNDEFINED:
        return 'undefined'
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, int | float):
        if isinstance(value, float) and math.isnan(value):
            return 'NaN'
        if isinstance(value, float) and math.isinf(value):
            return 'Infinity' if value > 0 else '-Infinity'
        return 'number'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, list):
        return 'array'
    return 'object'


def _invalid_type(expected: str, value: Any) -> str:
    return f'Invalid input: expected {expected}, received {_received(value)}'


Check = Callable[[Any], Any]


class Rule:
    """Cadeia de checagens de um campo, no espírito de `z.string().trim().min(1)`.

    `message` é a mensagem do próprio schema (`z.number('...')`): vale para toda
    checagem sem mensagem própria, como no Zod 4.
    """

    def __init__(self, base: Check, message: str | None = None) -> None:
        self._checks: list[Check] = [base]
        self._optional = False
        self.message = message

    def _msg(self, own: str | None, default: str) -> str:
        return own or self.message or default

    def _add(self, check: Check) -> 'Rule':
        self._checks.append(check)
        return self

    def optional(self) -> 'Rule':
        self._optional = True
        return self

    def __call__(self, value: Any) -> Any:
        if self._optional and value is UNDEFINED:
            return UNDEFINED
        messages: list[str] = []
        for check in self._checks:
            try:
                value = check(value)
            except Issue as issue:
                messages.append(issue.message)
                if issue.abort:
                    break
        if messages:
            raise Issues(messages)
        return value

    # ---------------------------------------------------------------- texto
    def trim(self) -> 'Rule':
        return self._add(js_trim)

    def min_length(self, n: int, message: str | None = None) -> 'Rule':
        def check(v: str) -> str:
            if len(v) < n:  # o Zod 4 conta pontos de código, não unidades UTF-16
                raise Issue(self._msg(message, f'Too small: expected string to have >={n} characters'), abort=False)
            return v

        return self._add(check)

    def max_length(self, n: int, message: str | None = None) -> 'Rule':
        def check(v: str) -> str:
            if len(v) > n:
                raise Issue(self._msg(message, f'Too big: expected string to have <={n} characters'), abort=False)
            return v

        return self._add(check)

    def matches(self, pattern: re.Pattern[str], message: str) -> 'Rule':
        def check(v: str) -> str:
            if not pattern.fullmatch(v):
                raise Issue(self._msg(message, message), abort=False)
            return v

        return self._add(check)

    # ---------------------------------------------------------------- números
    def integer(self, message: str | None = None) -> 'Rule':
        def check(v: float) -> float | int:
            if not float(v).is_integer():
                raise Issue(self._msg(message, 'Invalid input: expected int, received number'))
            if v > MAX_SAFE_INTEGER:
                raise Issue(self._msg(message, f'Too big: expected int to be <={MAX_SAFE_INTEGER}'), abort=False)
            if v < -MAX_SAFE_INTEGER:
                raise Issue(self._msg(message, f'Too small: expected int to be >={-MAX_SAFE_INTEGER}'), abort=False)
            return int(v)  # 100.0 do JSON vira 100: dinheiro sempre `int` (Const. 1.1)

        return self._add(check)

    def gt(self, n: int, message: str | None = None) -> 'Rule':
        def check(v: float) -> float:
            if not v > n:
                raise Issue(self._msg(message, f'Too small: expected number to be >{n}'), abort=False)
            return v

        return self._add(check)

    def ge(self, n: int, message: str | None = None) -> 'Rule':
        def check(v: float) -> float:
            if not v >= n:
                raise Issue(self._msg(message, f'Too small: expected number to be >={n}'), abort=False)
            return v

        return self._add(check)

    def le(self, n: int, message: str | None = None) -> 'Rule':
        def check(v: float) -> float:
            if not v <= n:
                raise Issue(self._msg(message, f'Too big: expected number to be <={n}'), abort=False)
            return v

        return self._add(check)


def string(message: str | None = None) -> Rule:
    def base(v: Any) -> str:
        if not isinstance(v, str):
            raise Issue(message or _invalid_type('string', v))
        return v

    return Rule(base, message)


def number(message: str | None = None) -> Rule:
    def base(v: Any) -> float | int:
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
            raise Issue(message or _invalid_type('number', v))
        return v

    return Rule(base, message)


def email() -> Rule:
    return string().matches(EMAIL_RE, 'Invalid email address')


def uuid(message: str | None = None) -> Rule:
    return string(message).matches(UUID_RE, message or 'Invalid UUID')


def iso_datetime(message: str) -> Rule:
    return string(message).matches(ISO_DATETIME_RE, message)


def enum(values: Sequence[str], message: str) -> Rule:
    def base(v: Any) -> str:
        if not isinstance(v, str) or v not in values:
            raise Issue(message)
        return v

    return Rule(base, message)


def _pydantic(rule: Rule) -> Callable[[Any], Any]:
    def validate(value: Any) -> Any:
        try:
            return rule(value)
        except Issues as issues:
            raise PydanticCustomError('zod', '{messages}', {'messages': issues.messages}) from None

    return validate


class Schema:
    """Objeto Zod: um modelo Pydantic com um campo por regra; chaves desconhecidas são descartadas."""

    def __init__(self, title: str, /, **fields: Rule) -> None:
        definitions: dict[str, Any] = {
            key: (Annotated[Any, PlainValidator(_pydantic(rule))], Field(default=UNDEFINED, validate_default=True))
            for key, rule in fields.items()
        }
        self.model: type[BaseModel] = create_model(
            title, __config__=ConfigDict(extra='ignore', arbitrary_types_allowed=True), **definitions
        )

    def parse(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            # Erro no próprio objeto: o Zod o põe em `formErrors`, e `fieldErrors` fica vazio.
            raise validation_error({})
        try:
            parsed = self.model.model_validate(data)
        except ValidationError as err:
            issues: dict[str, list[str]] = {}
            for e in err.errors():
                issues.setdefault(str(e['loc'][0]), []).extend((e.get('ctx') or {})['messages'])
            raise validation_error(issues) from None
        return {k: v for k, v in parsed.model_dump().items() if v is not UNDEFINED}


def parse_value(rule: Rule, value: Any) -> Any:
    """Valor solto (parâmetro de rota, cabeçalho): erro sem campo, `issues` vazio."""
    try:
        return rule(value)
    except Issues:
        raise validation_error({}) from None


def validation_error(issues: dict[str, list[str]]) -> AppError:
    return AppError('VALIDATION', 'Entrada inválida', {'issues': issues})
