import asyncio
from typing import Any, TypedDict

from leilao.db import Db, Tx, with_tx
from leilao.services.context import AppContext, WalletChangedEvent


class WalletSummary(TypedDict):
    balance_cents: int
    committed_cents: int
    available_cents: int


async def deposit(
    ctx: AppContext, user_id: str, amount_cents: int, idempotency_key: str | None = None
) -> tuple[WalletSummary, bool]:
    """Depósito simulado (suposição S1 da 001). Trava só a carteira — nunca um lote (Const. 2.2).

    Com `idempotency_key`, a mesma confirmação repetida vira um único lançamento: o
    `INSERT ... ON CONFLICT DO NOTHING` decide, e o saldo só soma se a linha for nova
    (spec 004, S-09). Devolve o resumo e `replayed`.
    """

    async def run(tx: Tx) -> bool:
        await tx.query('SELECT 1 FROM wallets WHERE user_id = $1 FOR UPDATE', [user_id])
        entry = await tx.query(
            """INSERT INTO ledger_entries (user_id, kind, amount_cents, idempotency_key) VALUES ($1, 'deposit', $2, $3)
       ON CONFLICT (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING RETURNING id""",
            [user_id, amount_cents, idempotency_key],
        )
        if not entry.rowcount:
            return False
        await tx.query(
            'UPDATE wallets SET balance_cents = balance_cents + $2, updated_at = clock_timestamp() WHERE user_id = $1',
            [user_id, amount_cents],
        )
        return True

    inserted = await with_tx(ctx.db, run)
    summary = await wallet_summary(ctx.db, user_id)
    if inserted:  # só após COMMIT
        await ctx.events.emit('wallet:changed', WalletChangedEvent(user_id=user_id, **summary))
    return summary, not inserted


async def wallet_summary(db: Db, user_id: str) -> WalletSummary:
    res = await db.query(
        """SELECT w.balance_cents,
            COALESCE((SELECT SUM(current_price_cents) FROM lots
                       WHERE status = 'open' AND leader_user_id = w.user_id), 0)::bigint AS committed_cents
       FROM wallets w WHERE w.user_id = $1""",
        [user_id],
    )
    row = res.rows[0] if res.rows else {}
    balance = int(row.get('balance_cents', 0))
    committed = int(row.get('committed_cents', 0))
    return {'balance_cents': balance, 'committed_cents': committed, 'available_cents': balance - committed}


async def wallet_detail(db: Db, user_id: str) -> dict[str, Any]:
    """Carteira com os lotes que compõem o comprometido (FR-007, FR-008 da 004). Tudo derivado (Const. 1.4)."""
    summary, lots = await asyncio.gather(
        wallet_summary(db, user_id),
        db.query(
            """SELECT id AS lot_id, title, current_price_cents AS amount_cents
         FROM lots WHERE status = 'open' AND leader_user_id = $1 ORDER BY ends_at""",
            [user_id],
        ),
    )
    return {**summary, 'committed_lots': lots.rows}
