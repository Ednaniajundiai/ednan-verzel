import inspect
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

import psycopg
from psycopg.rows import dict_row
from psycopg.types.string import TextLoader
from psycopg_pool import AsyncConnectionPool

log = logging.getLogger('leilao.db')

Row = dict[str, Any]
T = TypeVar('T')
Hook = Callable[[], Any]


@dataclass
class Result:
    rows: list[Row]
    rowcount: int


@lru_cache(maxsize=512)
def _paramstyle(sql: str) -> str:
    """O SQL é o mesmo do backend Node (`$1`, `$2`…); o psycopg usa `%(p1)s`."""
    return re.sub(r'\$(\d+)', r'%(p\1)s', sql.replace('%', '%%'))


async def _run(conn: psycopg.AsyncConnection[Row], sql: str, params: Sequence[Any] | None) -> Result:
    if params is None:
        cur = await conn.execute(sql.encode())  # sem parâmetros: aceita vários comandos (migrations)
    else:
        cur = await conn.execute(_paramstyle(sql), {f'p{i}': v for i, v in enumerate(params, 1)})
    rows = await cur.fetchall() if cur.description else []
    return Result(rows, cur.rowcount)


async def _configure(conn: psycopg.AsyncConnection[Any]) -> None:
    # UUID volta como texto, como no `pg` do Node (ids comparados e serializados como string).
    conn.adapters.register_loader('uuid', TextLoader)


class Db:
    """Pool de conexões. `query` roda fora de transação explícita (autocommit), como `pool.query` do `pg`."""

    def __init__(self, pool: AsyncConnectionPool[psycopg.AsyncConnection[Row]]) -> None:
        self.pool = pool

    async def query(self, sql: str, params: Sequence[Any] | None = None) -> Result:
        async with self.pool.connection() as conn:
            return await _run(conn, sql, params)

    async def close(self) -> None:
        await self.pool.close()


class Tx:
    """Conexão dentro de `with_tx`. `after_commit` agenda algo para depois do COMMIT."""

    def __init__(self, conn: psycopg.AsyncConnection[Row]) -> None:
        self.conn = conn
        self.hooks: list[Hook] = []

    async def query(self, sql: str, params: Sequence[Any] | None = None) -> Result:
        return await _run(self.conn, sql, params)

    def after_commit(self, hook: Hook) -> None:
        self.hooks.append(hook)


Queryable = Db | Tx


async def create_pool(url: str, max_size: int = 20) -> Db:
    pool: AsyncConnectionPool[psycopg.AsyncConnection[Row]] = AsyncConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        open=False,
        configure=_configure,
        # prepare_threshold=None: sem prepared statements implícitos, como o `pg`.
        kwargs={'row_factory': dict_row, 'autocommit': True, 'prepare_threshold': None},
    )
    await pool.open(wait=True)
    return Db(pool)


async def with_tx[T](db: Db, fn: Callable[[Tx], Awaitable[T]]) -> T:
    async with db.pool.connection() as conn:
        # Um Tx por transação: o gancho nunca sobrevive à conexão devolvida ao pool.
        tx = Tx(conn)
        try:
            await conn.execute('BEGIN')
            result = await fn(tx)
            await conn.execute('COMMIT')
        except BaseException:
            try:
                await conn.execute('ROLLBACK')
            except Exception:
                pass
            raise
    # Depois do COMMIT: falha aqui não desfaz nada nem chega ao chamador (S-05 da 004).
    for hook in tx.hooks:
        try:
            value = hook()
            if inspect.isawaitable(value):
                await value
        except Exception:
            log.exception('[db] afterCommit falhou')
    return result


async def migrate(db: Db, directory: Path) -> None:
    await db.query(
        'CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())'
    )
    for file in sorted(p for p in directory.iterdir() if p.name.endswith('.sql')):  # noqa: ASYNC240 (só no boot)
        found = await db.query('SELECT 1 FROM schema_migrations WHERE name = $1', [file.name])
        if found.rowcount:
            continue
        sql = file.read_text(encoding='utf-8')

        async def apply(tx: Tx, sql: str = sql, name: str = file.name) -> None:
            await tx.query(sql)
            await tx.query('INSERT INTO schema_migrations (name) VALUES ($1)', [name])

        await with_tx(db, apply)


def sqlstate(err: BaseException) -> str | None:
    """Código SQLSTATE do erro do banco (o `err.code` do `pg`)."""
    return getattr(err, 'sqlstate', None)
