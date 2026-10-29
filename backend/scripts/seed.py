"""Seed de demonstração: 2 leiloeiros, 3 clientes (licitantes) e lotes em todos os estados — ao vivo
com lances, ao vivo perto do fim (para ver o anti-sniping), agendado, encerrado arrematado e
encerrado sem vencedor.

As camisas vêm da TheSportsDB quando ela responde; senão, de camisas locais de reserva (SVG), para
a demonstração nunca subir vazia. Idempotente: se o leiloeiro demo já tem lotes, só garante as
contas. `uv run python -m scripts.seed`
"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from leilao.config import load_config
from leilao.db import create_pool, migrate
from leilao.lib.errors import AppError
from leilao.lib.jsjson import iso, js_collapse_ws
from leilao.services.auction import create_lot, place_bid, settle_lot
from leilao.services.audit import AuditSigner
from leilao.services.catalog import list_saved_jerseys, search_teams, strip_diacritics
from leilao.services.context import AppContext, CatalogDeps, LotRules
from leilao.services.thesportsdb import TheSportsDbClient
from leilao.services.users import authenticate, register_user
from leilao.services.wallet import deposit
from leilao.services.witness import WitnessLog
from scripts.seed_jerseys import LOCAL_JERSEYS, jersey_svg

SEED_PASSWORD = 'demo-verzel'

# 'auctioneer' é o dono dos lotes semeados.
SEED_USERS = [
    {'key': 'auctioneer', 'username': 'daniel_castello', 'name': 'Daniel Castello', 'role': 'auctioneer'},
    {'key': 'filipe', 'username': 'filipe_carvalho', 'name': 'Filipe Carvalho', 'role': 'auctioneer'},
    {'key': 'heloisa', 'username': 'heloisa_barcala', 'name': 'Heloisa Barcala', 'role': 'bidder'},
    {'key': 'luiz', 'username': 'luiz_spinelli', 'name': 'Luiz Spinelli', 'role': 'bidder'},
    {'key': 'alan', 'username': 'alan_franzin', 'name': 'Alan Franzin', 'role': 'bidder'},
]

BIDDER_DEPOSIT_CENTS = 500_000  # R$ 5.000,00
MIN = 60_000


def log(message: str) -> None:
    print(f'[seed] {message}', flush=True)


async def main() -> None:
    config = load_config()
    db = await create_pool(config.database_url)
    try:
        await migrate(db, config.migrations_dir)
        signer = AuditSigner.load(config.audit_private_key_pem, config.storage_dir)
        witness = WitnessLog(config.witness_file, signer)
        witness.load()
        ctx = AppContext(
            db=db,
            signer=signer,
            witness=witness,
            pseudonym_secret=config.pseudonym_secret,
            receipt_secret=config.receipt_secret,
            catalog=CatalogDeps(
                client=TheSportsDbClient(config.thesportsdb_base_url, timeout_ms=5_000),
                storage_dir=config.storage_dir,
                ttl_hours=config.catalog_ttl_hours,
            ),
            rules=LotRules(),
        )
        await seed(ctx, config.storage_dir)
    finally:
        await db.close()


async def seed(ctx: AppContext, storage_dir: Path) -> None:
    ids: dict[str, str] = {}
    for u in SEED_USERS:
        try:
            user = await authenticate(ctx.db, u['username'], SEED_PASSWORD)
        except AppError:
            user = await register_user(
                ctx.db, username=u['username'], password=SEED_PASSWORD, role=u['role'], name=u['name']
            )
            if u['role'] == 'bidder':
                await deposit(ctx, user['id'], BIDDER_DEPOSIT_CENTS)
        ids[u['key']] = user['id']
        log(f'{"leiloeiro" if u["role"] == "auctioneer" else "cliente"} {u["username"]} / {SEED_PASSWORD}')

    existing = await ctx.db.query('SELECT 1 FROM lots WHERE auctioneer_id = $1 LIMIT 1', [ids['auctioneer']])
    if existing.rowcount:
        log('lotes de demonstração já existem; nada a criar')
        return

    # ------------------------------------------------------------ camisas
    jerseys: list[dict[str, Any]] = []
    for team in ('Flamengo', 'Palmeiras'):
        res = await search_teams(ctx, team)
        if res.get('notice'):
            log(f'fonte de camisas indisponível ({res["notice"]["code"]}); usando camisas locais')
            break
        jerseys.extend(j for j in res['jerseys'] or [] if j['image_status'] == 'saved')
    if len(jerseys) < 5:
        images = storage_dir / 'images'
        images.mkdir(parents=True, exist_ok=True)
        for j in LOCAL_JERSEYS:
            file = f'seed-{j.key}.svg'
            (images / file).write_text(jersey_svg(j), encoding='utf-8')
            team_id = 'seed-' + js_collapse_ws(strip_diacritics(j.team).lower()).replace(' ', '-')
            await ctx.db.query(
                """INSERT INTO catalog_teams (external_id, name, league, country) VALUES ($1, $2, $3, 'Brazil')
       ON CONFLICT (external_id) DO NOTHING""",
                [team_id, j.team, j.league],
            )
            label = 'titular' if j.kind == '1st' else 'reserva'
            await ctx.db.query(
                """INSERT INTO items (external_id, source, title, image_path, team_external_id, season, kind, fetched_at)
       VALUES ($1, 'seed', $2, $3, $4, $5, $6, now())
       ON CONFLICT (external_id) DO UPDATE SET image_path = EXCLUDED.image_path""",
                [f'seed:{j.key}', f'Camisa {j.team} {j.season} {label}', file, team_id, j.season, j.kind],
            )
        saved = (await list_saved_jerseys(ctx))['jerseys']
        jerseys.extend(j for j in saved if not any(x['id'] == j['id'] for x in jerseys))

    # ------------------------------------------------------------ lotes
    def pick(i: int) -> dict[str, Any]:
        return jerseys[i % len(jerseys)]

    def at(ms: int) -> str:
        """`new Date(Date.now() + ms).toISOString()`."""
        return iso(datetime.now(UTC) + timedelta(milliseconds=ms))

    async def lot(j: dict[str, Any], *, ends_in: int, start: int, inc: int, starts_in: int = 0, size: str = 'M') -> str:
        payload: dict[str, Any] = {
            'item_id': j['id'],
            'title': j['title'],
            'size': size,
            'condition': 'nova',
            'ends_at': at(ends_in),
            'starting_price_cents': start,
            'min_increment_cents': inc,
        }
        if starts_in:
            payload['starts_at'] = at(starts_in)
        return (await create_lot(ctx, ids['auctioneer'], payload))['id']

    live_with_bids = await lot(pick(0), ends_in=30 * MIN, start=15_000, inc=1_000)
    await place_bid(ctx, user_id=ids['heloisa'], lot_id=live_with_bids, amount_cents=15_000)
    await place_bid(ctx, user_id=ids['luiz'], lot_id=live_with_bids, amount_cents=17_000)
    await place_bid(ctx, user_id=ids['heloisa'], lot_id=live_with_bids, amount_cents=19_000)
    log(f'ao vivo com 3 lances: {live_with_bids} (encerra em 30 min)')

    closing = await lot(pick(1), ends_in=5 * MIN, start=20_000, inc=1_000, size='G')
    log(f'ao vivo perto do fim: {closing} (encerra em 5 min; lance nos últimos 2 min prorroga)')

    scheduled = await lot(pick(2), starts_in=10 * MIN, ends_in=70 * MIN, start=12_000, inc=500)
    log(f'agendado: {scheduled} (começa em 10 min)')

    # Encerrados de verdade: lotes curtos, liquidados pelo próprio motor. O lance cai nos últimos
    # 2 min, então a prorrogação fica desligada só para ele.
    sold = await lot(pick(3), ends_in=2_500, start=25_000, inc=1_000)
    unsold = await lot(pick(4), ends_in=2_500, start=30_000, inc=1_000)
    ctx.rules = LotRules(extension_window_ms=0, extension_ms=0)
    await place_bid(ctx, user_id=ids['luiz'], lot_id=sold, amount_cents=25_000)
    ctx.rules = LotRules()
    await asyncio.sleep(3)
    await settle_lot(ctx, sold)
    await settle_lot(ctx, unsold)
    log(f'encerrado arrematado por R$ 250,00: {sold}')
    log(f'encerrado sem vencedor: {unsold}')


if __name__ == '__main__':
    asyncio.run(main())
