"""Cliente da TheSportsDB (D-03 da 002). Nunca lança: todo resultado é `Ok`, `RateLimited` ou
`Unavailable`, para que a busca degrade com aviso em vez de quebrar. O disjuntor fica em memória
(instância única, como o Socket.IO) e respeita o `Retry-After` informado pela fonte."""

import asyncio
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, TypeVar
from urllib.parse import quote

import httpx

from leilao.lib.jsjson import js_json_parse

T = TypeVar('T')


@dataclass
class Ok[T]:
    data: T
    kind: str = 'ok'


@dataclass
class RateLimited:
    retry_after_seconds: int
    kind: str = 'rate_limited'


@dataclass
class Unavailable:
    reason: str
    kind: str = 'unavailable'


Failure = RateLimited | Unavailable


@dataclass
class Image:
    content_type: str
    body: bytes


# Sem `Retry-After`, a espera assumida (a fonte costuma pedir ~116 s).
DEFAULT_RETRY_AFTER_SECONDS = 120
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _encode_uri_component(s: str) -> str:
    return quote(s, safe="-_.!~*'()")


def _truthy(v: Any) -> bool:
    """Veracidade do JavaScript para valores vindos de JSON."""
    return v not in (None, False, 0, '') and not (isinstance(v, float) and math.isnan(v))


class TheSportsDbClient:
    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_ms: int = 8_000,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.base_url = re.sub(r'/+$', '', base_url)
        self._transport = transport
        self.timeout_ms = timeout_ms
        # Relógio do disjuntor, em ms; injetável nos testes.
        self._now = now or (lambda: time.time() * 1000)
        self._blocked_until = 0.0

    def blocked_for_seconds(self) -> int:
        """Segundos até a fonte aceitar consultas de novo (0 = disjuntor fechado)."""
        return max(0, math.ceil((self._blocked_until - self._now()) / 1000))

    async def search_teams(self, name: str) -> Ok[list[dict[str, Any]]] | Failure:
        res = await self._get_json(f'/searchteams.php?t={_encode_uri_component(name)}')
        if not isinstance(res, Ok):
            return res
        teams = res.data.get('teams', ...) if isinstance(res.data, dict) else ...
        if teams is not None and not isinstance(teams, list):
            return Unavailable('formato inesperado')
        valid = [
            t
            for t in teams or []
            if isinstance(t, dict) and isinstance(t.get('idTeam'), str) and _truthy(t.get('strTeam'))
        ]
        # A busca da fonte mistura esportes ("Flamengo" do basquete); o leilão é de camisas de futebol.
        return Ok([t for t in valid if not _truthy(t.get('strSport')) or t.get('strSport') == 'Soccer'])

    async def lookup_equipment(self, team_id: str) -> Ok[list[dict[str, Any]]] | Failure:
        res = await self._get_json(f'/lookupequipment.php?id={_encode_uri_component(team_id)}')
        if not isinstance(res, Ok):
            return res
        equipment = res.data.get('equipment', ...) if isinstance(res.data, dict) else ...
        if equipment is not None and not isinstance(equipment, list):
            return Unavailable('formato inesperado')
        return Ok([e for e in equipment or [] if isinstance(e, dict) and isinstance(e.get('idEquipment'), str)])

    async def fetch_image(self, url: str) -> Ok[Image] | Failure:
        """Imagem em tamanho médio (sufixo `/medium`), pelo mesmo disjuntor."""
        res = await self._request(re.sub(r'/+$', '', url) + '/medium')
        if not isinstance(res, Ok):
            return res
        content_type = res.data.headers.get('content-type', '').split(';')[0].strip()
        if not content_type.startswith('image/'):
            return Unavailable(f'não é imagem ({content_type})')
        body = res.data.content
        if len(body) > MAX_IMAGE_BYTES:
            return Unavailable('imagem maior que 5 MB')
        return Ok(Image(content_type, body))

    async def _get_json(self, path: str) -> Ok[Any] | Failure:
        res = await self._request(f'{self.base_url}{path}')
        if not isinstance(res, Ok):
            return res
        try:
            # `Response.text()` do fetch: sempre UTF-8, sem BOM.
            data = js_json_parse(res.data.content.decode('utf-8-sig', 'replace'))
        except ValueError:
            # Ex.: página HTML de erro com status 200.
            return Unavailable('resposta não é JSON')
        if not isinstance(data, dict | list):
            return Unavailable('formato inesperado')
        return Ok(data)

    async def _request(self, url: str) -> Ok[httpx.Response] | Failure:
        blocked = self.blocked_for_seconds()
        if blocked > 0:
            return RateLimited(blocked)
        try:
            # O tempo-limite cobre a conexão e o corpo, como o `AbortSignal.timeout` do Node.
            async with asyncio.timeout(self.timeout_ms / 1000):
                async with httpx.AsyncClient(transport=self._transport, follow_redirects=True, timeout=None) as client:
                    res = await client.get(url)
        except TimeoutError:
            return Unavailable('The operation was aborted due to timeout')
        except Exception as err:
            return Unavailable(str(err) or 'falha de rede')
        if res.status_code == 429:
            seconds = parse_retry_after(res.headers.get('retry-after'), self._now())
            self._blocked_until = self._now() + seconds * 1000
            return RateLimited(seconds)
        if not 200 <= res.status_code < 300:
            return Unavailable(f'HTTP {res.status_code}')
        return Ok(res)


def parse_retry_after(header: str | None, now_ms: float) -> int:
    """`Retry-After` em segundos ou como data HTTP; ausente ou inválido → 120 s."""
    if not header:
        return DEFAULT_RETRY_AFTER_SECONDS
    trimmed = header.strip()
    if re.fullmatch(r'[0-9]+', trimmed):
        return max(1, int(trimmed))
    date: datetime | None = None
    try:
        date = parsedate_to_datetime(trimmed)
    except (TypeError, ValueError):
        try:
            date = datetime.fromisoformat(trimmed)
        except ValueError:
            date = None
    if date is not None:
        if date.tzinfo is None:
            date = date.astimezone()
        return max(1, math.ceil((date.timestamp() * 1000 - now_ms) / 1000))
    return DEFAULT_RETRY_AFTER_SECONDS
