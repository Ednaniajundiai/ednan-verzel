"""Rotas HTTP (o `app.ts` do Node), sem o prefixo `/api`, que o nginx e o Vite removem.

Além das rotas, reproduz o que no Express virava contrato: corpo JSON lido antes do roteamento
(JSON inválido → 400 mesmo sem login), método errado → 404, `/auctioneer/*` checa o papel antes de
procurar a rota, barra final aceita e o envelope `{error: {code, message, ...detalhes}}`.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import jwt
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.responses import JSONResponse as _JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from leilao.http import schemas
from leilao.lib import validation as z
from leilao.lib.errors import AppError
from leilao.lib.jsjson import iso, js_json_parse
from leilao.services.auction import (
    PHASE_SQL,
    cancel_lot,
    create_lot,
    get_lot,
    list_auctioneer_lots,
    list_lots,
    place_bid,
)
from leilao.services.audit import list_audit_entries, verify_lot
from leilao.services.catalog import list_jerseys, list_saved_jerseys, search_teams
from leilao.services.context import AppContext
from leilao.services.participations import list_participations
from leilao.services.receipts import get_receipt
from leilao.services.users import ROLES, authenticate, get_user, register_user
from leilao.services.wallet import deposit, wallet_detail, wallet_summary

log = logging.getLogger('leilao.http')

JSON_LIMIT = 32 * 1024  # express.json({ limit: '32kb' })


class JSONResponse(_JSONResponse):
    # Mesmo cabeçalho do `res.json` do Express.
    media_type = 'application/json; charset=utf-8'


TOKEN_TTL_SECONDS = 12 * 3600


# ---------------------------------------------------------------- tokens


def sign_token(secret: str, user_id: str, role: str) -> str:
    now = int(time.time())
    return jwt.encode({'role': role, 'iat': now, 'exp': now + TOKEN_TTL_SECONDS, 'sub': user_id}, secret, 'HS256')


def verify_token(secret: str, token: str) -> dict[str, str] | None:
    """Token sem `role` (emitido antes da 002) não vale mais (FR-002 da 002)."""
    try:
        payload = jwt.decode(token, secret, algorithms=['HS256'], options={'verify_aud': False})
    except Exception:
        return None
    sub = payload.get('sub')
    role = payload.get('role')
    if not isinstance(sub, str) or not sub or role not in ROLES:
        return None
    return {'userId': sub, 'role': role}


# ---------------------------------------------------------------- corpo JSON (express.json)


def _is_json(content_type: str) -> bool:
    return content_type.split(';')[0].strip().lower() == 'application/json'


def _error_response(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse({'error': {'code': code, 'message': message, **(details or {})}}, status_code=status)


class JsonBodyMiddleware:
    """Lê e interpreta o corpo JSON de toda requisição antes do roteamento, como o `express.json`.

    O resultado fica em `scope['state']['json_body']` (`UNDEFINED` sem corpo JSON). Também remove
    uma barra final do caminho (o Express não diferencia `/lots` de `/lots/`).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        path: str = scope['path']
        if len(path) > 1 and path.endswith('/'):
            scope = {**scope, 'path': path.rstrip('/') or '/'}

        headers = {k.decode('latin-1').lower(): v.decode('latin-1') for k, v in scope['headers']}
        chunks: list[bytes] = []
        size = 0
        more = True
        while more:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            size += len(chunk)
            if size <= JSON_LIMIT + 1:
                chunks.append(chunk)
            more = message.get('more_body', False)
        body = b''.join(chunks)

        parsed: Any = z.UNDEFINED
        if _is_json(headers.get('content-type', '')):
            if size > JSON_LIMIT:
                # O Express responde 413 do body-parser, que o tratador de erros do app vira 500.
                await _error_response(500, 'INTERNAL', 'Erro interno')(scope, receive, send)
                return
            try:
                text = body.decode('utf-8')
                stripped = text.lstrip(' \t\n\r')
                if not stripped:
                    parsed = {}
                elif stripped[0] not in '{[':
                    raise ValueError('strict')  # body-parser em modo estrito: só objeto ou lista
                else:
                    parsed = js_json_parse(text)
            except ValueError:
                await _error_response(400, 'VALIDATION', 'JSON inválido')(scope, receive, send)
                return
        scope.setdefault('state', {})['json_body'] = parsed

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return await receive()

        await self.app(scope, replay, send)


class PrefixGuardMiddleware:
    """Checagem que vale para um prefixo inteiro, inclusive para rotas que não existem."""

    def __init__(self, app: ASGIApp, prefix: str, guard: Callable[[dict[str, str]], AppError | None]) -> None:
        self.app = app
        self.prefix = prefix
        self.guard = guard

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get('path', '')
        if scope['type'] == 'http' and (path == self.prefix or path.startswith(self.prefix + '/')):
            headers = {k.decode('latin-1').lower(): v.decode('latin-1') for k, v in scope['headers']}
            err = self.guard(headers)
            if err:
                await _error_response(err.status, err.code, err.message, err.details)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def ok(data: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status)


def json_body(request: Request) -> Any:
    return request.scope.get('state', {}).get('json_body', z.UNDEFINED)


def _query(request: Request) -> dict[str, Any]:
    """`req.query` do Express 5 (parser simples): chave repetida vira lista."""
    out: dict[str, Any] = {}
    for key in request.query_params:
        values = request.query_params.getlist(key)
        out[key] = values if len(values) > 1 else values[0]
    return out


# ---------------------------------------------------------------- app

IMAGE_TYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
}


def create_app(ctx: AppContext, *, jwt_secret: str, storage_dir: Path) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)

    def claims(request: Request) -> dict[str, str] | None:
        header = request.headers.get('authorization')
        return verify_token(jwt_secret, header[7:]) if header and header.startswith('Bearer ') else None

    def viewer_id(request: Request) -> str | None:
        c = claims(request)
        return c['userId'] if c else None

    def require_user(request: Request) -> str:
        c = claims(request)
        if not c:
            raise AppError('UNAUTHORIZED', 'Token ausente ou inválido')
        return c['userId']

    def require_role(request: Request, role: str) -> None:
        """Guarda de rota por papel (D-07 da 002): 401 sem login, 403 com o papel errado."""
        c = claims(request)
        if not c:
            raise AppError('UNAUTHORIZED', 'Token ausente ou inválido')
        if c['role'] != role:
            raise AppError('FORBIDDEN', 'Ação não permitida para o seu papel')

    def idempotency_key(request: Request) -> str | None:
        key = z.parse_value(schemas.idempotency_key, request.headers.get('idempotency-key', z.UNDEFINED))
        return None if key is z.UNDEFINED else key

    async def server_now() -> str:
        res = await ctx.db.query('SELECT clock_timestamp() AS now')
        return iso(res.rows[0]['now'])

    @app.exception_handler(AppError)
    async def app_error(_request: Request, err: AppError) -> JSONResponse:
        return _error_response(err.status, err.code, err.message, err.details)

    @app.exception_handler(404)
    @app.exception_handler(405)
    async def not_found(_request: Request, _err: Exception) -> JSONResponse:
        # Método errado também cai no "rota não encontrada", como no Express.
        return _error_response(404, 'NOT_FOUND', 'Rota não encontrada')

    @app.exception_handler(Exception)
    async def internal(_request: Request, _err: Exception) -> JSONResponse:
        # O uvicorn registra o traceback; o cliente só vê o código genérico.
        return _error_response(500, 'INTERNAL', 'Erro interno')

    def auctioneer_guard(headers: dict[str, str]) -> AppError | None:
        # `app.use('/auctioneer', requireRole('auctioneer'), router)`: o papel vem antes da rota.
        header = headers.get('authorization')
        c = verify_token(jwt_secret, header[7:]) if header and header.startswith('Bearer ') else None
        if not c:
            return AppError('UNAUTHORIZED', 'Token ausente ou inválido')
        if c['role'] != 'auctioneer':
            return AppError('FORBIDDEN', 'Ação não permitida para o seu papel')
        return None

    # O último middleware adicionado é o mais externo: o corpo é lido antes da guarda, como no Express.
    app.add_middleware(PrefixGuardMiddleware, prefix='/auctioneer', guard=auctioneer_guard)
    app.add_middleware(JsonBodyMiddleware)

    @app.get('/health')
    async def health() -> Response:
        await ctx.db.query('SELECT 1')
        return ok({'status': 'ok'})

    # ------------------------------------------------------------ auth
    @app.post('/auth/register')
    async def register(request: Request) -> Response:
        body = schemas.register.parse(json_body(request))
        user = await register_user(ctx.db, **body)
        return ok({'token': sign_token(jwt_secret, user['id'], user['role']), 'user': user}, 201)

    @app.post('/auth/login')
    async def login(request: Request) -> Response:
        body = schemas.login.parse(json_body(request))
        user = await authenticate(ctx.db, body['username'], body['password'])
        return ok({'token': sign_token(jwt_secret, user['id'], user['role']), 'user': user})

    @app.get('/me')
    async def me(request: Request) -> Response:
        user_id = require_user(request)
        return ok({'user': await get_user(ctx.db, user_id), 'wallet': await wallet_summary(ctx.db, user_id)})

    # ------------------------------------------------------------ meus arremates (só licitante, spec 004)
    @app.get('/me/participations')
    async def participations(request: Request) -> Response:
        require_role(request, 'bidder')
        listed, now = await asyncio.gather(list_participations(ctx, require_user(request)), server_now())
        return ok({'server_now': now, **listed})

    # ------------------------------------------------------------ carteira (só licitante, spec 004)
    @app.get('/wallet')
    async def wallet(request: Request) -> Response:
        require_role(request, 'bidder')
        return ok(await wallet_detail(ctx.db, require_user(request)))

    @app.post('/wallet/deposit')
    async def wallet_deposit(request: Request) -> Response:
        require_role(request, 'bidder')
        user_id = require_user(request)
        body = schemas.deposit.parse(json_body(request))
        key = idempotency_key(request)
        summary, replayed = await deposit(ctx, user_id, body['amount_cents'], key)
        return ok({'wallet': summary, 'replayed': replayed})

    # ------------------------------------------------------------ lotes e lances
    @app.get('/lots')
    async def lots(request: Request) -> Response:
        listed, now = await asyncio.gather(list_lots(ctx, viewer_id(request)), server_now())
        return ok({'server_now': now, 'lots': listed})

    @app.get('/lots/{lot_id}')
    async def lot(request: Request, lot_id: str) -> Response:
        lot_id = z.parse_value(schemas.uuid, lot_id)
        found, now = await asyncio.gather(get_lot(ctx, lot_id, viewer_id(request)), server_now())
        return ok({'server_now': now, 'lot': found})

    @app.post('/lots/{lot_id}/bids')
    async def bid(request: Request, lot_id: str) -> Response:
        user_id = require_user(request)
        lot_id = z.parse_value(schemas.uuid, lot_id)
        body = schemas.bid.parse(json_body(request))
        key = idempotency_key(request)
        result = await place_bid(
            ctx, user_id=user_id, lot_id=lot_id, amount_cents=body['amount_cents'], idempotency_key=key
        )
        return ok(
            {'bid': result.to_json(), 'wallet': await wallet_summary(ctx.db, user_id)},
            200 if result.replayed else 201,
        )

    # ------------------------------------------------------------ leiloeiro (D-07 da 002)
    # Catálogo de camisas (FR-006 a FR-010 da 002): fonte fora do ar responde 200 com `notice`.
    @app.get('/auctioneer/catalog/teams')
    async def catalog_teams(request: Request) -> Response:
        q = schemas.catalog_query.parse(_query(request))['q']
        return ok(await search_teams(ctx, q))

    @app.get('/auctioneer/catalog/teams/{team_id}/jerseys')
    async def catalog_jerseys(team_id: str) -> Response:
        return ok(await list_jerseys(ctx, z.parse_value(schemas.team_id, team_id)))

    @app.get('/auctioneer/catalog/jerseys')
    async def catalog_saved() -> Response:
        return ok(await list_saved_jerseys(ctx))

    # Lotes do leiloeiro (FR-011 a FR-018 da 002): a validação por campo fica no serviço.
    @app.get('/auctioneer/lots')
    async def auctioneer_lots(request: Request) -> Response:
        panel, now = await asyncio.gather(list_auctioneer_lots(ctx, require_user(request)), server_now())
        return ok({'server_now': now, **panel})

    @app.post('/auctioneer/lots')
    async def auctioneer_create(request: Request) -> Response:
        return ok(await create_lot(ctx, require_user(request), json_body(request)), 201)

    @app.post('/auctioneer/lots/{lot_id}/cancel')
    async def auctioneer_cancel(request: Request, lot_id: str) -> Response:
        lot_id = z.parse_value(schemas.uuid, lot_id)
        return ok(await cancel_lot(ctx, auctioneer_id=require_user(request), lot_id=lot_id))

    # ------------------------------------------------------------ auditoria pública
    # Comprovante público, por link não adivinhável (spec 004, H4).
    @app.get('/receipts/{receipt}')
    async def receipt(receipt: str) -> Response:
        return ok(await get_receipt(ctx, receipt[:200]))

    @app.get('/audit/public-key')
    async def public_key() -> PlainTextResponse:
        return PlainTextResponse(ctx.signer.public_key_pem)

    # Histórico completo + dados do lote (só a cópia local, FR-006) + veredito (spec 004, S-11).
    @app.get('/audit/lots/{lot_id}')
    async def audit_lot(lot_id: str) -> Response:
        lot_id = z.parse_value(schemas.uuid, lot_id)
        lot = await _get_audit_lot(ctx, lot_id)
        verdict = await verify_lot(ctx.db, ctx.signer, ctx.witness, ctx.pseudonym_secret, lot_id)
        witness = verdict.pop('witness')
        return ok(
            {
                'lot_id': lot_id,
                'algorithm': 'sha256+ed25519',
                'entries': await list_audit_entries(ctx.db, lot_id),
                'lot': lot,
                'witness': witness,
                'verdict': verdict,
            }
        )

    @app.get('/audit/lots/{lot_id}/verify')
    async def audit_verify(lot_id: str) -> Response:
        lot_id = z.parse_value(schemas.uuid, lot_id)
        verdict = await verify_lot(ctx.db, ctx.signer, ctx.witness, ctx.pseudonym_secret, lot_id)
        verdict.pop('witness')
        return ok(verdict)

    # ------------------------------------------------------------ estáticos
    images_dir = (Path(storage_dir) / 'images').resolve()

    @app.api_route('/images/{name:path}', methods=['GET', 'HEAD'])
    async def images(name: str) -> Response:
        # express.static: arquivos com nome iniciado em ponto e caminhos fora da pasta não existem.
        file = (images_dir / name).resolve()
        if (
            images_dir not in file.parents
            or any(part.startswith('.') for part in Path(name).parts)
            or not file.is_file()
        ):
            raise AppError('NOT_FOUND', 'Rota não encontrada')
        return FileResponse(
            file,
            media_type=IMAGE_TYPES.get(file.suffix.lower(), 'application/octet-stream'),
            headers={'Cache-Control': 'public, max-age=2592000, immutable'},
        )

    return app


async def _get_audit_lot(ctx: AppContext, lot_id: str) -> dict[str, Any]:
    """Dados públicos do lote para a auditoria: só a cópia local, sem dono nem licitantes."""
    res = await ctx.db.query(
        f"""SELECT l.id, l.title, l.image_path, l.attributes, l.size, l.condition, l.status, l.starts_at, l.ends_at,
            l.starting_price_cents, l.current_price_cents, l.bid_count, l.audit_head_hash, {PHASE_SQL} AS phase
       FROM lots l, LATERAL (SELECT clock_timestamp() AS now) c WHERE l.id = $1""",
        [lot_id],
    )
    if not res.rows:
        raise AppError('NOT_FOUND', 'Lote não encontrado')
    lot = res.rows[0]
    return {
        'id': lot['id'],
        'title': lot['title'],
        'image_url': f'/images/{lot["image_path"]}' if lot['image_path'] else None,
        'attributes': lot['attributes'],
        'size': lot['size'],
        'condition': lot['condition'],
        'status': lot['status'],
        'phase': lot['phase'],
        'starts_at': iso(lot['starts_at']),
        'ends_at': iso(lot['ends_at']),
        'starting_price_cents': lot['starting_price_cents'],
        'current_price_cents': lot['current_price_cents'],
        'bid_count': lot['bid_count'],
        'audit_head_hash': lot['audit_head_hash'],
    }
