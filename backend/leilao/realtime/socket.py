"""Salas: `lot:<id>` (pública, só pseudônimos), `lots` (listagem geral, recebe eventos de todos os
lotes) e `user:<id>` (privada: "você foi superado", "você venceu", carteira). Instância única;
para escalar horizontalmente, usar um `AsyncRedisManager` do python-socketio."""

import re
from typing import Any

import socketio

from leilao.http.app import verify_token
from leilao.services.context import AppContext, BidPlacedEvent, LotCancelledEvent, LotSettledEvent, WalletChangedEvent

_LOT_ID = re.compile(r'[0-9a-f-]{36}', re.IGNORECASE)


def attach_realtime(ctx: AppContext, jwt_secret: str) -> socketio.AsyncServer:
    # cors_allowed_origins=[]: sem cabeçalhos CORS e sem recusar por origem, como `cors: { origin: false }`.
    sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins=[])

    @sio.event
    async def connect(sid: str, _environ: dict[str, Any], auth: Any = None) -> None:
        token = auth.get('token') if isinstance(auth, dict) else None
        claims = verify_token(jwt_secret, token) if isinstance(token, str) else None
        await sio.enter_room(sid, 'lots')
        if claims:
            await sio.enter_room(sid, f'user:{claims["userId"]}')

    @sio.on('lot:join')
    async def lot_join(sid: str, *args: Any) -> None:
        lot_id = args[0] if args else None
        if isinstance(lot_id, str) and _LOT_ID.fullmatch(lot_id):
            await sio.enter_room(sid, f'lot:{lot_id}')

    @sio.on('lot:leave')
    async def lot_leave(sid: str, *args: Any) -> None:
        lot_id = args[0] if args else None
        if isinstance(lot_id, str):
            await sio.leave_room(sid, f'lot:{lot_id}')

    async def on_bid_placed(e: BidPlacedEvent) -> None:
        rooms = [f'lot:{e.lot_id}', 'lots']
        await sio.emit(
            'bid:placed',
            {
                'lot_id': e.lot_id,
                'bid_id': e.bid_id,
                'bidder': e.bidder,
                'amount_cents': e.amount_cents,
                'bid_count': e.bid_count,
                'at': e.at,
                'ends_at': e.ends_at,
            },
            to=rooms,
        )
        if e.previous_ends_at:
            await sio.emit(
                'lot:extended',
                {'lot_id': e.lot_id, 'ends_at': e.ends_at, 'previous_ends_at': e.previous_ends_at},
                to=rooms,
            )
        if e.outbid_user_id:
            await sio.emit(
                'bid:outbid', {'lot_id': e.lot_id, 'amount_cents': e.amount_cents}, to=f'user:{e.outbid_user_id}'
            )

    # D-15 da 002: cancelamento chega à sala do lote e à listagem geral (vitrine da 003).
    async def on_lot_cancelled(e: LotCancelledEvent) -> None:
        await sio.emit('lot:cancelled', {'lot_id': e.lot_id}, to=[f'lot:{e.lot_id}', 'lots'])

    # Privado: só o próprio usuário recebe (spec 004, D-04).
    async def on_wallet_changed(e: WalletChangedEvent) -> None:
        await sio.emit(
            'wallet:changed',
            {
                'balance_cents': e.balance_cents,
                'committed_cents': e.committed_cents,
                'available_cents': e.available_cents,
            },
            to=f'user:{e.user_id}',
        )

    async def on_lot_settled(e: LotSettledEvent) -> None:
        await sio.emit(
            'lot:settled',
            {
                'lot_id': e.lot_id,
                'status': e.status,
                'winner': e.winner,
                'final_price_cents': e.final_price_cents,
                'at': e.at,
            },
            to=[f'lot:{e.lot_id}', 'lots'],
        )
        if e.winner_user_id:
            await sio.emit(
                'lot:won', {'lot_id': e.lot_id, 'final_price_cents': e.final_price_cents}, to=f'user:{e.winner_user_id}'
            )

    ctx.events.on('bid:placed', on_bid_placed)
    ctx.events.on('lot:cancelled', on_lot_cancelled)
    ctx.events.on('wallet:changed', on_wallet_changed)
    ctx.events.on('lot:settled', on_lot_settled)
    return sio
