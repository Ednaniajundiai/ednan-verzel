"""Cria a conta de administrador (leiloeiro) se ela ainda não existe. Idempotente: nunca troca a
senha de uma conta existente. Lê ADMIN_USERNAME e ADMIN_PASSWORD (mín. 8) do ambiente.
`uv run python -m scripts.create_admin`
"""

import asyncio
import os
import sys

from leilao.config import load_config
from leilao.db import create_pool
from leilao.http.schemas import register
from leilao.lib.errors import AppError
from leilao.services.users import register_user


async def main() -> int:
    try:
        data = register.parse(
            {
                'username': os.environ.get('ADMIN_USERNAME', ''),
                'password': os.environ.get('ADMIN_PASSWORD', ''),
                'role': 'auctioneer',
            }
        )
    except AppError as err:
        print(f'[admin] ADMIN_USERNAME/ADMIN_PASSWORD inválidos; conta não criada: {err.details}', flush=True)
        return 1
    db = await create_pool(load_config().database_url)
    try:
        try:
            await register_user(db, **data)
            print(f'[admin] conta criada: {data["username"]} (leiloeiro)', flush=True)
        except AppError as err:
            if err.code != 'CONFLICT':
                raise
            print(f'[admin] {data["username"]} já existe; nada a fazer', flush=True)
    finally:
        await db.close()
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
