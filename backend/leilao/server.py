"""Ponto de entrada da API (`python -m leilao.server`): migra, carrega a chave e a testemunha,
monta o HTTP e o Socket.IO no mesmo app ASGI e sobe o job de liquidação."""

import asyncio
import logging
from pathlib import Path

import socketio
import uvicorn

from leilao.config import load_config
from leilao.db import create_pool, migrate
from leilao.http.app import create_app
from leilao.realtime.socket import attach_realtime
from leilao.services.auction import start_settlement_scheduler
from leilao.services.audit import AuditSigner
from leilao.services.context import AppContext, CatalogDeps, LotRules
from leilao.services.thesportsdb import TheSportsDbClient
from leilao.services.witness import WitnessLog

log = logging.getLogger('leilao.api')


def build_asgi(ctx: AppContext, jwt_secret: str, storage_dir: Path) -> socketio.ASGIApp:
    """HTTP (FastAPI) e Socket.IO (`/socket.io`) num app só, na mesma porta, como no Node."""
    app = create_app(ctx, jwt_secret=jwt_secret, storage_dir=storage_dir)
    sio = attach_realtime(ctx, jwt_secret)
    return socketio.ASGIApp(sio, other_asgi_app=app, socketio_path='socket.io')


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    config = load_config()
    db = await create_pool(config.database_url, config.db_pool_max)
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
            client=TheSportsDbClient(config.thesportsdb_base_url),
            storage_dir=config.storage_dir,
            ttl_hours=config.catalog_ttl_hours,
        ),
        rules=LotRules(),
    )

    asgi = build_asgi(ctx, config.jwt_secret, config.storage_dir)
    stop_scheduler = start_settlement_scheduler(
        ctx, config.settlement_interval_ms, lambda err: log.error('[settlement] falha na rodada', exc_info=err)
    )
    server = uvicorn.Server(uvicorn.Config(asgi, host='0.0.0.0', port=config.port, lifespan='off', log_level='info'))
    log.info('[api] ouvindo em http://localhost:%s', config.port)
    try:
        await server.serve()  # SIGTERM/SIGINT encerram o uvicorn
    finally:
        log.info('[api] encerrando')
        stop_scheduler()
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
