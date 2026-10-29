"""Compatibilidade byte a byte com o backend Node (spec 005, D-05 e D-06).

A trilha de auditoria guarda textos gerados por `JSON.stringify` e instantes
gerados por `Date.prototype.toISOString`. Para que um elo gravado por um
backend continue íntegro no outro, estas funções reproduzem as regras do
JavaScript em vez de usar as do Python (`json.dumps` escapa e ordena de outro
jeito; `isoformat` não trunca para milissegundos).
"""

import base64
import binascii
import json
import math
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

# `\s` do JavaScript: WhiteSpace + LineTerminator (o que `trim()` remove).
_JS_WS = '\t\n\v\f\r    -     　﻿'
_JS_WS_RUN = re.compile(f'[{_JS_WS}]+')
_JS_TRIM = re.compile(f'^[{_JS_WS}]+|[{_JS_WS}]+$')

_SHORT_ESCAPES = {'"': '\\"', '\\': '\\\\', '\b': '\\b', '\f': '\\f', '\n': '\\n', '\r': '\\r', '\t': '\\t'}


def js_trim(s: str) -> str:
    return _JS_TRIM.sub('', s)


def js_collapse_ws(s: str) -> str:
    """`s.replace(/\\s+/g, ' ')`."""
    return _JS_WS_RUN.sub(' ', s)


def js_length(s: str) -> int:
    """`s.length`: unidades UTF-16, não pontos de código."""
    return len(s.encode('utf-16-le', 'surrogatepass')) // 2


def js_string(s: str) -> str:
    """`JSON.stringify(s)` para uma string (escapes do ES2019, inclusive surrogates isolados)."""
    out = ['"']
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        code = ord(ch)
        if ch in _SHORT_ESCAPES:
            out.append(_SHORT_ESCAPES[ch])
        elif code < 0x20:
            out.append(f'\\u{code:04x}')
        elif 0xD800 <= code <= 0xDBFF and i + 1 < n and 0xDC00 <= ord(s[i + 1]) <= 0xDFFF:
            # Par de surrogates separado no `str`: no JavaScript é um caractere só.
            out.append(chr(0x10000 + ((code - 0xD800) << 10) + (ord(s[i + 1]) - 0xDC00)))
            i += 1
        elif 0xD800 <= code <= 0xDFFF:
            out.append(f'\\u{code:04x}')
        else:
            out.append(ch)
        i += 1
    out.append('"')
    return ''.join(out)


def js_number(value: float | int) -> str:
    """`Number.prototype.toString` (o que `JSON.stringify` usa para números)."""
    if isinstance(value, bool):
        raise TypeError('bool não é número')
    if isinstance(value, int):
        if abs(value) <= 2**53:
            return str(value)
        value = float(value)
    if not math.isfinite(value):
        return 'null'
    if value == 0:
        return '0'
    # Dígitos mínimos que reconstroem o double (o `repr` do Python e o JS usam o mesmo critério).
    sign, digits_t, exp = Decimal(repr(value)).normalize().as_tuple()
    digits = ''.join(map(str, digits_t))
    k = len(digits)
    n = int(exp) + k  # posição do ponto decimal
    if k <= n <= 21:
        text = digits + '0' * (n - k)
    elif 0 < n <= 21:
        text = f'{digits[:n]}.{digits[n:]}'
    elif -6 < n <= 0:
        text = f'0.{"0" * -n}{digits}'
    else:
        e = n - 1
        mantissa = digits if k == 1 else f'{digits[0]}.{digits[1:]}'
        text = f'{mantissa}e{"+" if e >= 0 else "-"}{abs(e)}'
    return ('-' if sign else '') + text


def _utf16_key(k: str) -> bytes:
    return k.encode('utf-16-be', 'surrogatepass')


def canonical_json(value: Any) -> str:
    """JSON com chaves ordenadas recursivamente: a mesma entrada sempre gera os mesmos bytes (`canonicalJson` do Node)."""
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, str):
        return js_string(value)
    if isinstance(value, int | float):
        return js_number(value)
    if isinstance(value, list | tuple):
        return '[' + ','.join(canonical_json(v) for v in value) + ']'
    if isinstance(value, dict):
        keys = sorted(value.keys(), key=_utf16_key)
        return '{' + ','.join(f'{js_string(k)}:{canonical_json(value[k])}' for k in keys) + '}'
    raise TypeError(f'tipo não serializável: {type(value).__name__}')


def iso(dt: datetime) -> str:
    """`Date.prototype.toISOString()` de um `timestamptz` lido pelo `pg`: UTC, truncado em milissegundos."""
    u = dt.astimezone(UTC)
    return f'{u:%Y-%m-%dT%H:%M:%S}.{u.microsecond // 1000:03d}Z'


def iso_or_none(dt: datetime | None) -> str | None:
    return iso(dt) if dt is not None else None


def now_iso() -> str:
    """`new Date().toISOString()`: relógio da aplicação, em milissegundos."""
    return iso(datetime.now(UTC))


_B64_CHARS = re.compile(r'[^A-Za-z0-9+/]')


def node_b64decode(text: str) -> bytes:
    """`Buffer.from(text, 'base64')`: tolerante como o Node (ignora lixo, aceita base64url, para no `=`)."""
    clean = _B64_CHARS.sub('', text.replace('-', '+').replace('_', '/').split('=', 1)[0])
    if len(clean) % 4 == 1:
        clean = clean[:-1]
    try:
        return base64.b64decode(clean + '=' * (-len(clean) % 4))
    except binascii.Error:
        return b''


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def b64url(data: bytes) -> str:
    """`digest('base64url')`: sem preenchimento."""
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _reject_constant(name: str) -> Any:
    raise ValueError(f'JSON inválido: {name}')


def js_json_parse(text: str | bytes) -> Any:
    """`JSON.parse`: recusa `NaN` e `Infinity`, que o `json` do Python aceita."""
    return json.loads(text, parse_constant=_reject_constant)
