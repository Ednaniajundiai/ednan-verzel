from typing import TYPE_CHECKING, Any

from leilao.db import Row
from leilao.lib.jsjson import iso, iso_or_none
from leilao.services.auction import PHASE_SQL, settle_due
from leilao.services.receipts import receipt_id

if TYPE_CHECKING:
    from leilao.services.context import AppContext


async def list_participations(ctx: 'AppContext', user_id: str) -> dict[str, Any]:
    """ "Meus arremates" (spec 004, H3): lotes em que o licitante deu lance, ao vivo ("participando")
    ou encerrados (arrematado, com comprovante, ou não). Só os dados do próprio usuário; a fase vem
    do relógio do banco (003)."""
    await settle_due(ctx, 'AND id IN (SELECT lot_id FROM bids WHERE user_id = $1)', [user_id])
    res = await ctx.db.query(
        f"""SELECT l.id AS lot_id, l.title, l.image_path, l.status, {PHASE_SQL} AS phase, l.current_price_cents,
            l.leader_user_id = $1 AS leading, m.max_cents AS my_max_cents, l.ends_at, l.settled_at
       FROM (SELECT lot_id, max(amount_cents)::bigint AS max_cents FROM bids WHERE user_id = $1 GROUP BY lot_id) m
       JOIN lots l ON l.id = m.lot_id, LATERAL (SELECT clock_timestamp() AS now) c
      ORDER BY l.ends_at DESC""",
        [user_id],
    )

    def image(r: Row) -> str | None:
        return f'/images/{r["image_path"]}' if r['image_path'] else None

    def closed(r: Row) -> dict[str, Any]:
        won = r['status'] == 'settled' and r['leading']
        item: dict[str, Any] = {
            'lot_id': r['lot_id'],
            'title': r['title'],
            'image_url': image(r),
            'outcome': 'won' if won else 'lost',
            'final_price_cents': r['current_price_cents'] if r['status'] == 'settled' else None,
            'my_max_cents': r['my_max_cents'],
            'settled_at': iso_or_none(r['settled_at']),
        }
        if won:
            item['receipt_url'] = f'/comprovante/{receipt_id(ctx.receipt_secret, r["lot_id"])}'
        return item

    live = sorted(
        (r for r in res.rows if r['phase'] in ('live', 'scheduled')), key=lambda r: iso(r['ends_at'])
    )  # ms, como o `getTime()` do Node
    return {
        'participating': [
            {
                'lot_id': r['lot_id'],
                'title': r['title'],
                'image_url': image(r),
                'phase': r['phase'],
                'current_price_cents': r['current_price_cents'],
                'my_max_cents': r['my_max_cents'],
                'leading': r['leading'],
                'ends_at': iso(r['ends_at']),
            }
            for r in live
        ],
        'closed': [closed(r) for r in res.rows if r['phase'] == 'ended'],
    }
