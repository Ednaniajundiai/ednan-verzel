"""Porte de `db-aftercommit.test.ts`: withTx com afterCommit (S-05 da 004)."""

from collections.abc import AsyncIterator
from unittest.mock import Mock

import pytest
import pytest_asyncio

from leilao.db import Tx, with_tx
from leilao.services.context import AppContext


@pytest_asyncio.fixture(scope='module', autouse=True)
async def probe(ctx: AppContext) -> AsyncIterator[None]:
    await ctx.db.query('CREATE TABLE IF NOT EXISTS aftercommit_probe (v int)')
    await ctx.db.query('TRUNCATE aftercommit_probe')
    yield
    await ctx.db.query('DROP TABLE IF EXISTS aftercommit_probe')


async def test_callback_roda_depois_do_commit_vendo_o_dado_gravado(ctx: AppContext) -> None:
    seen: list[int] = []

    async def run(tx: Tx) -> None:
        await tx.query('INSERT INTO aftercommit_probe VALUES (1)')

        async def hook() -> None:
            res = await ctx.db.query('SELECT count(*)::int AS n FROM aftercommit_probe')
            seen.append(res.rows[0]['n'])

        tx.after_commit(hook)

    await with_tx(ctx.db, run)
    assert seen == [1]


async def test_nao_roda_em_rollback(ctx: AppContext) -> None:
    hook = Mock()

    async def run(tx: Tx) -> None:
        tx.after_commit(hook)
        raise RuntimeError('falha')

    with pytest.raises(RuntimeError, match='falha'):
        await with_tx(ctx.db, run)
    hook.assert_not_called()


async def test_erro_no_callback_nao_desfaz_a_transacao_nem_chega_ao_chamador(ctx: AppContext) -> None:
    async def run(tx: Tx) -> str:
        await tx.query('INSERT INTO aftercommit_probe VALUES (2)')

        def hook() -> None:
            raise RuntimeError('testemunha indisponível')

        tx.after_commit(hook)
        return 'ok'

    assert await with_tx(ctx.db, run) == 'ok'
    res = await ctx.db.query('SELECT count(*)::int AS n FROM aftercommit_probe WHERE v = 2')
    assert res.rows[0]['n'] == 1


async def test_o_gancho_nao_vaza_para_o_proximo_uso_da_mesma_conexao(ctx: AppContext) -> None:
    hook = Mock()

    async def first(tx: Tx) -> None:
        tx.after_commit(hook)

    async def second(_tx: Tx) -> None:
        return None

    await with_tx(ctx.db, first)
    hook.reset_mock()
    await with_tx(ctx.db, second)
    hook.assert_not_called()
