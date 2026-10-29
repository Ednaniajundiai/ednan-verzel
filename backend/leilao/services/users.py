from typing import Literal, TypedDict

from leilao.db import Db, Tx, sqlstate, with_tx
from leilao.lib.crypto import hash_password, verify_password
from leilao.lib.errors import AppError

ROLES: tuple[str, ...] = ('auctioneer', 'bidder')
Role = Literal['auctioneer', 'bidder']


class User(TypedDict):
    id: str
    username: str
    name: str
    role: Role


async def register_user(db: Db, *, username: str, password: str, role: str, name: str | None = None) -> User:
    """`name` é o nome exibido; sem ele, vale o próprio usuário."""
    password_hash = await hash_password(password)

    async def insert(tx: Tx) -> User:
        res = await tx.query(
            'INSERT INTO users (username, name, password_hash, role) VALUES ($1, $2, $3, $4) RETURNING id, username, name, role',
            [username, name or username, password_hash, role],
        )
        await tx.query('INSERT INTO wallets (user_id) VALUES ($1)', [res.rows[0]['id']])
        return _user(res.rows[0])

    try:
        return await with_tx(db, insert)
    except Exception as err:
        if sqlstate(err) == '23505':
            raise AppError('CONFLICT', 'Usuário já cadastrado') from None
        raise


async def authenticate(db: Db, username: str, password: str) -> User:
    res = await db.query(
        'SELECT id, username, name, role, password_hash FROM users WHERE lower(username) = lower($1)', [username]
    )
    user = res.rows[0] if res.rows else None
    # Mensagem única para usuário inexistente e senha errada: não revela quem tem conta.
    if not user or not await verify_password(password, user['password_hash']):
        raise AppError('UNAUTHORIZED', 'Credenciais inválidas')
    return _user(user)


async def get_user(db: Db, user_id: str) -> User:
    res = await db.query('SELECT id, username, name, role FROM users WHERE id = $1', [user_id])
    if not res.rows:
        raise AppError('UNAUTHORIZED', 'Usuário não encontrado')
    return _user(res.rows[0])


def _user(row: dict[str, object]) -> User:
    return {'id': str(row['id']), 'username': str(row['username']), 'name': str(row['name']), 'role': row['role']}  # type: ignore[typeddict-item]
