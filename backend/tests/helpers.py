"""Porte de `test/helpers.ts`: contexto contra PG real, fábricas e utilitários de concorrência."""

import asyncio
import contextlib
import itertools
import os
import tempfile
import time
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import socketio
import uvicorn

from leilao.config import ROOT
from leilao.db import Db, create_pool, migrate
from leilao.lib.errors import AppError
from leilao.lib.jsjson import iso
from leilao.server import build_asgi
from leilao.services.auction import create_lot
from leilao.services.audit import AuditSigner
from leilao.services.context import AppContext, CatalogDeps, LotRules
from leilao.services.thesportsdb import TheSportsDbClient
from leilao.services.users import User, register_user
from leilao.services.wallet import deposit
from leilao.services.witness import WitnessLog

TEST_DB = os.environ.get('TEST_DATABASE_URL', 'postgres://postgres@localhost:5432/leilao_test')
MIGRATIONS = ROOT / 'migrations'
FIXTURES = Path(__file__).parent / 'fixtures'

# Fonte externa que nunca responde: os testes não dependem da rede.
OFFLINE_SOURCE = 'http://127.0.0.1:1/api/v1/json/123'


async def setup_context() -> AppContext:
    db = await create_pool(TEST_DB)
    await migrate(db, MIGRATIONS)
    await reset_db(db)
    signer = AuditSigner.ephemeral()
    storage_dir = Path(tempfile.mkdtemp(prefix='leilao-storage-'))
    return AppContext(
        db=db,
        signer=signer,
        witness=WitnessLog(storage_dir / 'audit-witness.jsonl', signer),
        pseudonym_secret='test-pseudonym-secret',
        receipt_secret='test-receipt-secret',
        catalog=CatalogDeps(
            client=TheSportsDbClient(OFFLINE_SOURCE, timeout_ms=500), storage_dir=storage_dir, ttl_hours=24
        ),
        rules=LotRules(),
    )


async def reset_db(db: Db) -> None:
    # TRUNCATE não dispara o gatilho por linha que protege audit_log.
    await db.query(
        'TRUNCATE audit_log, ledger_entries, bids, lots, items, wallets, users, catalog_teams, catalog_team_searches CASCADE'
    )


_seq = itertools.count(1)


def _unique() -> str:
    return f'{next(_seq)}-{time.time_ns()}'


async def make_user(ctx: AppContext, balance_cents: int = 0, role: str = 'bidder') -> User:
    n = _unique()
    user = await register_user(ctx.db, username=f'usuario-teste-{n}', password='x' * 8, role=role)
    if balance_cents > 0:
        await deposit(ctx, user['id'], balance_cents)
    return user


async def make_auctioneer(ctx: AppContext) -> User:
    return await make_user(ctx, 0, 'auctioneer')


async def make_item(ctx: AppContext, image: str = 'saved') -> str:
    """Camisa de catálogo; por padrão já com a imagem salva localmente."""
    res = await ctx.db.query(
        """INSERT INTO items (external_id, source, title, image_path, image_source_url, season, kind)
     VALUES ($1, 'test', 'Camisa de teste', $2, $3, '2024', '1st') RETURNING id""",
        [
            f'test:{_unique()}',
            'teste.png' if image == 'saved' else None,
            None if image == 'none' else 'https://img.test/camisa.png',
        ],
    )
    return str(res.rows[0]['id'])


def in_ms(ms: int) -> str:
    """`new Date(Date.now() + ms).toISOString()`."""
    return iso(datetime.now(UTC) + timedelta(milliseconds=ms))


def lot_input(item_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        'item_id': item_id,
        'title': 'Camisa de teste',
        'size': 'M',
        'condition': 'nova',
        'ends_at': in_ms(3_600_000),
        'starting_price_cents': 100,
        'min_increment_cents': 10,
        **overrides,
    }


async def db_now(ctx: AppContext, offset_ms: int = 0) -> str:
    res = await ctx.db.query("SELECT clock_timestamp() + $1 * interval '1 millisecond' AS at", [offset_ms])
    return iso(res.rows[0]['at'])


async def make_lot(
    ctx: AppContext,
    *,
    duration_ms: int | None = None,
    starting_price_cents: int = 100,
    min_increment_cents: int = 10,
    auctioneer_id: str | None = None,
) -> str:
    """Lote ao vivo (início = agora pelo relógio do banco) de um leiloeiro. Com `duration_ms`, o fim
    é calculado pelo relógio do banco: a trilha (`lot_opened`) e o `original_ends_at` ficam coerentes."""
    owner = auctioneer_id or (await make_auctioneer(ctx))['id']
    item_id = await make_item(ctx)
    ends_at = in_ms(3_600_000) if duration_ms is None else await db_now(ctx, duration_ms)
    created = await create_lot(
        ctx,
        owner,
        lot_input(
            item_id,
            ends_at=ends_at,
            starting_price_cents=starting_price_cents,
            min_increment_cents=min_increment_cents,
        ),
    )
    return created['id']


async def expire_lot(ctx: AppContext, lot_id: str) -> None:
    """Helper de ADULTERAÇÃO: muda o fim direto no banco, fora da trilha. Simula "fim já passou e
    ainda não foi liquidado"; depois dele, a verificação acusa `ends_at_mismatch` (o esperado)."""
    await ctx.db.query("UPDATE lots SET ends_at = clock_timestamp() - interval '1 millisecond' WHERE id = $1", [lot_id])


async def lot_row(ctx: AppContext, lot_id: str) -> dict[str, Any]:
    res = await ctx.db.query('SELECT * FROM lots WHERE id = $1', [lot_id])
    return res.rows[0]


async def sleep(ms: float) -> None:
    await asyncio.sleep(ms / 1000)


async def outcome(aw: Awaitable[Any]) -> str:
    """Executa e devolve o código do erro (ou 'OK'): facilita contar resultados de chamadas paralelas."""
    try:
        await aw
        return 'OK'
    except AppError as err:
        return err.code
    except Exception as err:
        return getattr(err, 'sqlstate', None) or repr(err)


def count_by(values: list[str]) -> dict[str, int]:
    return dict(Counter(values))


async def gather(*aws: Awaitable[Any]) -> list[Any]:
    return list(await asyncio.gather(*aws))


async def wait_db_clock(ctx: AppContext, instant_iso: str, margin_ms: int = 0) -> None:
    """Espera o relógio do banco passar de `instant_iso` + `margin_ms` (spec 005, D-09)."""
    while True:
        res = await ctx.db.query(
            "SELECT clock_timestamp() >= $1::timestamptz + $2 * interval '1 millisecond' AS past",
            [instant_iso, margin_ms],
        )
        if res.rows[0]['past']:
            return
        await asyncio.sleep(0.02)


# ---------------------------------------------------------------- servidor e clientes


@contextlib.asynccontextmanager
async def running_server(ctx: AppContext, jwt_secret: str, storage_dir: Path | None = None) -> AsyncIterator[str]:
    """Sobe o app ASGI completo (HTTP + Socket.IO) num uvicorn real, numa porta livre."""
    asgi = build_asgi(ctx, jwt_secret, storage_dir or ctx.catalog.storage_dir)
    server = uvicorn.Server(
        uvicorn.Config(asgi, host='127.0.0.1', port=0, lifespan='off', log_level='warning', access_log=False)
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        if task.done():
            task.result()
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        await task


class Api:
    """`fetch` com JSON, como o `api()` dos testes Node."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.client = httpx.AsyncClient(base_url=base, timeout=30, trust_env=False)

    async def __call__(
        self, method: str, path: str, body: Any = None, headers: dict[str, str] | None = None, token: str | None = None
    ) -> tuple[int, Any]:
        h = {'content-type': 'application/json', **(headers or {})}
        if token:
            h['authorization'] = f'Bearer {token}'
        content = None if body is None else httpx.Request('POST', '/', json=body).content
        res = await self.client.request(method, path, content=content, headers=h)
        return res.status_code, res.json()

    async def get(self, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
        return await self.client.get(path, headers=headers)

    async def close(self) -> None:
        await self.client.aclose()


async def connect_socket(base: str, token: str | None = None, lot_id: str | None = None) -> socketio.AsyncClient:
    s = socketio.AsyncClient()
    await s.connect(base, transports=['websocket'], auth={'token': token} if token else {}, wait_timeout=5)
    if lot_id:
        await s.emit('lot:join', lot_id)
        await sleep(30)
    return s


def record(s: socketio.AsyncClient) -> dict[str, list[Any]]:
    """Junta os eventos recebidos por nome (o `onAny` do socket.io-client)."""
    got: dict[str, list[Any]] = {}

    async def any_event(name: str, *args: Any) -> None:
        got.setdefault(name, []).append(args[0] if args else None)

    s.on('*', any_event)
    return got


def next_event(s: socketio.AsyncClient, name: str) -> 'asyncio.Future[Any]':
    fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

    def handler(*args: Any) -> None:
        if not fut.done():
            fut.set_result(args[0] if args else None)

    s.on(name, handler)
    return fut


def png_bytes() -> bytes:
    import base64

    return base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
    )


Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def mock_source(
    handler: Handler, *, timeout_ms: int = 8_000, now: Callable[[], float] | None = None
) -> TheSportsDbClient:
    """Fonte da TheSportsDB com respostas controladas (o `fetchImpl` dos testes Node)."""

    async def handle(request: httpx.Request) -> httpx.Response:
        result = handler(request)
        if isinstance(result, Awaitable):
            result = await result
        return result

    return TheSportsDbClient(
        'https://tsdb.test/api/v1/json/123', transport=httpx.MockTransport(handle), timeout_ms=timeout_ms, now=now
    )
