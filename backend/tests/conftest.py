from collections.abc import AsyncIterator

import pytest_asyncio

from leilao.services.context import AppContext
from tests.helpers import setup_context


@pytest_asyncio.fixture(scope='module')
async def ctx() -> AsyncIterator[AppContext]:
    """Um contexto por arquivo, como o `ctx ??= await setupContext()` dos testes Node."""
    context = await setup_context()
    try:
        yield context
    finally:
        await context.db.close()
