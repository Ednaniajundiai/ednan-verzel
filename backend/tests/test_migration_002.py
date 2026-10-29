"""Porte de `migration-002.test.ts`: migração sobre um banco que só conhece a 001 (D-04 da 002).
Usa um banco próprio, recriado a cada execução, para não interferir na base dos outros testes."""

import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
import pytest_asyncio

from leilao.db import Db, create_pool, migrate
from leilao.lib.errors import AppError
from leilao.services.users import authenticate
from tests.helpers import MIGRATIONS, TEST_DB

MIGRATION_DB = 'leilao_test_migration_002'
state: dict[str, str] = {}


async def admin(sql: str) -> None:
    async with await psycopg.AsyncConnection.connect(TEST_DB, autocommit=True) as conn:
        await conn.execute(sql.encode())


@pytest_asyncio.fixture(scope='module')
async def db() -> AsyncIterator[Db]:
    await admin(f'DROP DATABASE IF EXISTS {MIGRATION_DB} WITH (FORCE)')
    await admin(f'CREATE DATABASE {MIGRATION_DB}')
    url = urlsplit(TEST_DB)
    pool = await create_pool(urlunsplit(url._replace(path=f'/{MIGRATION_DB}')))

    # Só a 001.
    only001 = Path(tempfile.mkdtemp(prefix='mig-001-'))
    shutil.copyfile(MIGRATIONS / '001_init.sql', only001 / '001_init.sql')
    await migrate(pool, only001)

    user = await pool.query(
        "INSERT INTO users (email, name, password_hash) VALUES ('antigo@x.dev', 'Antigo', 'scrypt$a$b') RETURNING id"
    )
    state['old_user_id'] = user.rows[0]['id']
    await pool.query('INSERT INTO wallets (user_id, balance_cents) VALUES ($1, 1000)', [state['old_user_id']])
    item = await pool.query(
        "INSERT INTO items (external_id, source, title, image_path) VALUES ('dummyjson.com:1', 'dummyjson.com', 'Relógio', 'abc.png') RETURNING id"
    )
    lot = await pool.query(
        """INSERT INTO lots (item_id, starting_price_cents, min_increment_cents, starts_at, ends_at)
     VALUES ($1, 100, 10, now(), now() + interval '1 hour') RETURNING id""",
        [item.rows[0]['id']],
    )
    state['old_lot_id'] = lot.rows[0]['id']

    await migrate(pool, MIGRATIONS)  # aplica a 002 (e o que vier depois)
    yield pool
    await pool.close()
    await admin(f'DROP DATABASE IF EXISTS {MIGRATION_DB} WITH (FORCE)')


async def test_fr001_usuarios_existentes_viram_licitantes(db: Db) -> None:
    res = await db.query('SELECT role FROM users WHERE id = $1', [state['old_user_id']])
    assert res.rows[0]['role'] == 'bidder'


async def test_cria_a_conta_de_sistema_leiloeira_com_carteira_e_sem_login(db: Db) -> None:
    res = await db.query(
        "SELECT u.id, u.username, u.role, u.password_hash FROM users u JOIN wallets w ON w.user_id = u.id WHERE u.role = 'auctioneer'"
    )
    assert len(res.rows) == 1
    assert res.rows[0]['password_hash'] == '!'
    for password in ('!', ''):
        with pytest.raises(AppError) as err:
            await authenticate(db, res.rows[0]['username'], password)
        assert err.value.code == 'UNAUTHORIZED'


async def test_fr014_lote_antigo_pertence_a_conta_de_sistema_com_titulo_e_imagem(db: Db) -> None:
    res = await db.query(
        'SELECT l.title, l.image_path, u.role, u.password_hash FROM lots l JOIN users u ON u.id = l.auctioneer_id WHERE l.id = $1',
        [state['old_lot_id']],
    )
    assert res.rows[0] == {'title': 'Relógio', 'image_path': 'abc.png', 'role': 'auctioneer', 'password_hash': '!'}


async def test_os_check_aceitam_cancelled_e_settlement_credit(db: Db) -> None:
    with pytest.raises(psycopg.errors.CheckViolation, match='check'):
        await db.query("UPDATE users SET role = 'admin' WHERE id = $1", [state['old_user_id']])
    with pytest.raises(psycopg.errors.CheckViolation, match='check'):
        await db.query("UPDATE lots SET status = 'paused' WHERE id = $1", [state['old_lot_id']])
    await db.query("UPDATE lots SET status = 'cancelled', cancelled_at = now() WHERE id = $1", [state['old_lot_id']])
    await db.query(
        "INSERT INTO ledger_entries (user_id, kind, amount_cents) VALUES ($1, 'settlement_credit', 1)",
        [state['old_user_id']],
    )
    with pytest.raises(psycopg.errors.CheckViolation, match='check'):
        await db.query(
            "INSERT INTO ledger_entries (user_id, kind, amount_cents) VALUES ($1, 'refund', 1)", [state['old_user_id']]
        )


async def test_migration_005_deriva_o_usuario_do_email_das_contas_antigas(db: Db) -> None:
    res = await db.query('SELECT username, email FROM users WHERE id = $1', [state['old_user_id']])
    assert res.rows[0]['username'] == 'antigo'
    assert res.rows[0]['email'] == 'antigo@x.dev'
    system = await db.query("SELECT username FROM users WHERE email = 'sistema@casa-de-leiloes.invalid'")
    assert system.rows[0]['username'] == 'sistema'
