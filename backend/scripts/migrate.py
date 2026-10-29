"""Aplica as migrations SQL pendentes (`uv run python -m scripts.migrate`)."""

import asyncio

from leilao.config import load_config
from leilao.db import create_pool, migrate


async def main() -> None:
    config = load_config()
    db = await create_pool(config.database_url)
    try:
        await migrate(db, config.migrations_dir)
    finally:
        await db.close()
    print('[migrate] ok')


if __name__ == '__main__':
    asyncio.run(main())
