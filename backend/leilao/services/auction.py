import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from leilao.db import Db, Queryable, Row, Tx, sqlstate, with_tx
from leilao.lib import validation as z
from leilao.lib.crypto import bidder_pseudonym
from leilao.lib.errors import AppError
from leilao.lib.jsjson import iso, iso_or_none
from leilao.services.audit import append_audit_event
from leilao.services.catalog import ensure_image
from leilao.services.context import AppContext, BidPlacedEvent, LotCancelledEvent, LotSettledEvent

log = logging.getLogger('leilao.settlement')

LOCKED_LOT_COLUMNS = """id, auctioneer_id, status, starts_at, ends_at, starting_price_cents, min_increment_cents,
  current_price_cents, leader_user_id, bid_count, audit_seq, audit_head_hash"""


def iso_sql(expr: str) -> str:
    """Instante em ISO 8601 UTC com microssegundos, gerado no SQL (sem passar por `datetime`)."""
    return f"""to_char({expr} AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')"""


def _in_window_sql(now: str, ends_at: str, window_ms_param: str) -> str:
    """Últimos `window` ms antes do fim vigente, inclusive o limite (spec 003, casos de borda)."""
    return f"{now} >= {ends_at} - {window_ms_param}::bigint * interval '1 millisecond'"


async def _lot_clock(tx: Tx, lot_id: str, extension_window_ms: int = 0) -> Row:
    """Relógio de referência (Const. 3.1). Chamado sempre DEPOIS do lock do lote.

    A comparação com a janela acontece no SQL, em µs. `now` volta como texto para ser regravado
    sem perda de precisão; `ends_at` volta em ISO com µs.
    """
    res = await tx.query(
        f"""SELECT c.now::text AS now, c.now >= l.starts_at AS started, c.now >= l.ends_at AS ended,
            {_in_window_sql('c.now', 'l.ends_at', '$2')} AS in_extension_window,
            {iso_sql('l.ends_at')} AS ends_at
       FROM lots l, LATERAL (SELECT clock_timestamp() AS now) c WHERE l.id = $1""",
        [lot_id, extension_window_ms],
    )
    return res.rows[0]


async def in_extension_window(db: Db, now_iso: str, ends_at_iso: str, window_ms: int) -> bool:
    """O mesmo predicado da janela, com instantes fixos: permite testar a fronteira exata."""
    res = await db.query(
        f'SELECT {_in_window_sql("$1::timestamptz", "$2::timestamptz", "$3")} AS inside',
        [now_iso, ends_at_iso, window_ms],
    )
    return bool(res.rows[0]['inside'])


# ---------------------------------------------------------------- criação

LOT_SIZES = ('PP', 'P', 'M', 'G', 'GG', 'XGG')
LOT_CONDITIONS = ('nova_com_etiqueta', 'nova', 'usada')


def _cents() -> z.Rule:
    return (
        z.number('Informe um valor em centavos')
        .integer('Use centavos inteiros')
        .gt(0, 'Deve ser maior que zero')
        .le(1_000_000_000_00)
    )


def _iso_date() -> z.Rule:
    return z.iso_datetime('Data e hora inválidas')


# Entrada da criação de lote, no formato da API (FR-011, FR-012 da 002).
lot_input_schema = z.Schema(
    'LotInput',
    item_id=z.uuid('Escolha uma camisa'),
    title=z.string('Informe o título')
    .trim()
    .min_length(1, 'Informe o título')
    .max_length(120, 'Use até 120 caracteres'),
    size=z.enum(LOT_SIZES, 'Escolha um tamanho'),
    condition=z.enum(LOT_CONDITIONS, 'Escolha o estado de conservação'),
    starts_at=_iso_date().optional(),
    ends_at=_iso_date(),
    starting_price_cents=_cents(),
    min_increment_cents=_cents(),
)

ITEM_FOR_LOT_SQL = """SELECT i.id, i.external_id, i.title, i.image_path, i.season, i.kind, t.name AS team_name, t.league
  FROM items i LEFT JOIN catalog_teams t ON t.external_id = i.team_external_id WHERE i.id = $1"""


async def create_lot(ctx: AppContext, auctioneer_id: str, raw: Any) -> dict[str, str]:
    """Cria um lote do leiloeiro a partir de uma camisa do catálogo (FR-010 a FR-014 da 002).
    A imagem é garantida antes, fora da transação; a janela é validada pelo relógio do banco."""
    data = lot_input_schema.parse(raw)

    await ensure_image(ctx, data['item_id'])

    async def run(tx: Tx) -> dict[str, str]:
        role = await tx.query('SELECT role FROM users WHERE id = $1', [auctioneer_id])
        if not role.rows or role.rows[0]['role'] != 'auctioneer':
            raise AppError('FORBIDDEN', 'Só leiloeiros criam lotes')

        item = await tx.query(ITEM_FOR_LOT_SQL, [data['item_id']])
        if not item.rows:
            raise AppError('NOT_FOUND', 'Camisa não encontrada')
        if not item.rows[0]['image_path']:
            raise AppError(
                'IMAGE_UNAVAILABLE', 'A imagem desta camisa está indisponível agora. Tente de novo em instantes.'
            )

        # Janela pelo relógio do banco: início "agora" aceito com 1 minuto de tolerância.
        window = await tx.query(
            """SELECT s.starts_at::text AS starts_at,
              s.starts_at >= c.now - interval '1 minute' AS start_ok,
              $2::timestamptz > s.starts_at AS end_ok
         FROM (SELECT clock_timestamp() AS now) c,
              LATERAL (SELECT COALESCE($1::timestamptz, c.now) AS starts_at) s""",
            [data.get('starts_at'), data['ends_at']],
        )
        w = window.rows[0]
        issues: dict[str, list[str]] = {}
        if not w['start_ok']:
            issues['starts_at'] = ['O início não pode estar no passado']
        if not w['end_ok']:
            issues['ends_at'] = ['O fim deve ser depois do início']
        if issues:
            raise z.validation_error(issues)

        return await _insert_lot(ctx, tx, auctioneer_id, item.rows[0], data, w['starts_at'])

    return await with_tx(ctx.db, run)


async def _insert_lot(
    ctx: AppContext, tx: Tx, auctioneer_id: str, item: Row, data: dict[str, Any], starts_at: str
) -> dict[str, str]:
    # Cópia dos atributos da camisa (D-09 da 002): o lote não muda se o catálogo mudar.
    attributes = {
        k: v
        for k, v in {
            'team': item['team_name'],
            'league': item['league'],
            'season': item['season'],
            'kind': item['kind'],
        }.items()
        if v is not None
    }
    res = await tx.query(
        # Fim em ms: o mesmo valor que vai, em ISO, para o lot_opened (sem falso ends_at_mismatch).
        f"""INSERT INTO lots (item_id, auctioneer_id, title, size, condition, attributes, image_path,
                       starting_price_cents, min_increment_cents, starts_at, ends_at, original_ends_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
             date_trunc('milliseconds', $11::timestamptz), date_trunc('milliseconds', $11::timestamptz))
     RETURNING {LOCKED_LOT_COLUMNS}""",
        [
            item['id'],
            auctioneer_id,
            data['title'],
            data['size'],
            data['condition'],
            json.dumps(attributes, ensure_ascii=False),
            item['image_path'],
            data['starting_price_cents'],
            data['min_increment_cents'],
            starts_at,
            data['ends_at'],
        ],
    )
    lot = res.rows[0]
    # O dono não entra no payload público da trilha (Art. 5.1).
    await append_audit_event(
        tx,
        ctx.signer,
        lot,
        'lot_opened',
        {
            'item_id': item['id'],
            'item_external_id': item['external_id'],
            'title': data['title'],
            'size': data['size'],
            'condition': data['condition'],
            'attributes': attributes,
            'starting_price_cents': lot['starting_price_cents'],
            'min_increment_cents': lot['min_increment_cents'],
            'starts_at': iso(lot['starts_at']),
            'ends_at': iso(lot['ends_at']),
        },
        ctx.witness,
    )
    return {'id': lot['id']}


# ---------------------------------------------------------------- lances (P1, P2)


@dataclass
class PlaceBidResult:
    bid_id: int
    lot_id: str
    amount_cents: int
    bidder: str
    at: str
    replayed: bool

    def to_json(self) -> dict[str, Any]:
        """Mesmos nomes do Node (camelCase): o front lê `bid.bidId`."""
        return {
            'bidId': self.bid_id,
            'lotId': self.lot_id,
            'amountCents': self.amount_cents,
            'bidder': self.bidder,
            'at': self.at,
            'replayed': self.replayed,
        }


async def place_bid(
    ctx: AppContext, *, user_id: str, lot_id: str, amount_cents: int, idempotency_key: str | None = None
) -> PlaceBidResult:
    if idempotency_key:
        replay = await _find_bid_by_key(ctx, ctx.db, user_id, idempotency_key)
        if replay:
            return replay

    try:
        result, event = await with_tx(
            ctx.db, lambda tx: _place_bid_tx(ctx, tx, user_id, lot_id, amount_cents, idempotency_key)
        )
    except Exception as err:
        # Corrida entre duas requisições com a mesma chave: a UNIQUE decide, a perdedora devolve a vencedora.
        if idempotency_key and sqlstate(err) == '23505':
            replay = await _find_bid_by_key(ctx, ctx.db, user_id, idempotency_key)
            if replay:
                return replay
        raise
    if event:
        await ctx.events.emit('bid:placed', event)  # só após COMMIT: ninguém é notificado de lance desfeito
    return result


async def _place_bid_tx(
    ctx: AppContext, tx: Tx, user_id: str, lot_id: str, amount_cents: int, idempotency_key: str | None
) -> tuple[PlaceBidResult, BidPlacedEvent | None]:
    # 0. Papel relido no banco, antes de tocar no lote (FR-003, D-07 da 002).
    role = await tx.query('SELECT role FROM users WHERE id = $1', [user_id])
    if not role.rows:
        raise AppError('UNAUTHORIZED', 'Usuário não encontrado')
    if role.rows[0]['role'] == 'auctioneer':
        raise AppError('AUCTIONEER_CANNOT_BID', 'Leiloeiros não dão lances')

    # 1. Lock do lote: serializa todos os lances deste lote.
    lot_res = await tx.query(f'SELECT {LOCKED_LOT_COLUMNS} FROM lots WHERE id = $1 FOR UPDATE', [lot_id])
    if not lot_res.rows:
        raise AppError('NOT_FOUND', 'Lote não encontrado')
    lot = lot_res.rows[0]

    # Reenvio que esperou na fila do lock atrás do original: devolve o original
    # em vez de avaliá-lo como lance novo (que cairia em ALREADY_LEADING).
    if idempotency_key:
        replay = await _find_bid_by_key(ctx, tx, user_id, idempotency_key)
        if replay:
            return replay, None

    # 2. Relógio lido após o lock: quem esperou na fila além do fim é rejeitado (CS4).
    clock = await _lot_clock(tx, lot['id'], ctx.rules.extension_window_ms)

    # 3. Recusas, na ordem da spec 003 (FR-005). O papel já foi checado antes do lock.
    if lot['status'] == 'cancelled':
        raise AppError('LOT_CANCELLED', 'Este lote foi cancelado')
    if lot['status'] == 'open' and not clock['started']:
        raise AppError('LOT_NOT_STARTED', 'Este lote ainda não começou', {'starts_at': iso(lot['starts_at'])})
    if lot['status'] != 'open' or clock['ended']:
        raise AppError('LOT_ENDED', 'Este lote já foi encerrado')
    if lot['leader_user_id'] == user_id:
        raise AppError('ALREADY_LEADING', 'Você já está ganhando este lote')
    minimum = (
        lot['starting_price_cents']
        if lot['current_price_cents'] is None
        else lot['current_price_cents'] + lot['min_increment_cents']
    )
    if amount_cents < minimum:
        raise AppError('BID_TOO_LOW', 'Lance abaixo do mínimo', {'minimum_cents': minimum})

    # 4. Lock da carteira (ordem lote → carteira, Const. 2.2) e saldo comprometido derivado (P2).
    wallet = await tx.query('SELECT balance_cents FROM wallets WHERE user_id = $1 FOR UPDATE', [user_id])
    balance = wallet.rows[0]['balance_cents'] if wallet.rows else 0
    committed = await tx.query(
        """SELECT COALESCE(SUM(current_price_cents), 0)::bigint AS committed
       FROM lots WHERE status = 'open' AND leader_user_id = $1 AND id <> $2""",
        [user_id, lot['id']],
    )
    available = balance - committed.rows[0]['committed']
    if available < amount_cents:
        raise AppError('INSUFFICIENT_FUNDS', 'Saldo insuficiente', {'available_cents': available})

    # 5. Efetiva.
    bid_res = await tx.query(
        # created_at = o instante da decisão, não um novo clock_timestamp(): o registro
        # precisa provar que o lance foi aceito antes do fim (CS4).
        """INSERT INTO bids (lot_id, user_id, amount_cents, idempotency_key, created_at)
     VALUES ($1, $2, $3, $4, $5) RETURNING id, created_at""",
        [lot['id'], user_id, amount_cents, idempotency_key, clock['now']],
    )
    bid = bid_res.rows[0]
    outbid_user_id = lot['leader_user_id']
    await tx.query(
        'UPDATE lots SET current_price_cents = $2, leader_user_id = $3, bid_count = bid_count + 1 WHERE id = $1',
        [lot['id'], amount_cents, user_id],
    )

    bidder = bidder_pseudonym(ctx.pseudonym_secret, user_id, lot['id'])
    at = iso(bid['created_at'])
    await append_audit_event(
        tx,
        ctx.signer,
        lot,
        'bid_placed',
        {'bid_id': bid['id'], 'bidder': bidder, 'amount_cents': amount_cents, 'at': at},
        ctx.witness,
    )

    # 6. Anti-sniping (FR-006, FR-007 da 003): na janela, o fim vai para o instante do lance +
    # prorrogação. GREATEST garante que o fim nunca diminui; o lote já está travado.
    ends_at = clock['ends_at']
    previous_ends_at: str | None = None
    if clock['in_extension_window'] and ctx.rules.extension_ms > 0:
        ext = await tx.query(
            f"""UPDATE lots SET ends_at = GREATEST(ends_at, $2::timestamptz + $3::bigint * interval '1 millisecond')
        WHERE id = $1 RETURNING {iso_sql('ends_at')} AS ends_at""",
            [lot['id'], clock['now'], ctx.rules.extension_ms],
        )
        if ext.rows[0]['ends_at'] != clock['ends_at']:
            previous_ends_at = clock['ends_at']
            ends_at = ext.rows[0]['ends_at']
            # Registrada junto ao lance que a causou (FR-008 da 003): o fim vigente fica verificável.
            await append_audit_event(
                tx,
                ctx.signer,
                lot,
                'lot_extended',
                {'bid_id': bid['id'], 'ends_at_before': previous_ends_at, 'ends_at_after': ends_at, 'at': at},
                ctx.witness,
            )

    result = PlaceBidResult(
        bid_id=bid['id'], lot_id=lot['id'], amount_cents=amount_cents, bidder=bidder, at=at, replayed=False
    )
    event = BidPlacedEvent(
        lot_id=lot['id'],
        bid_id=bid['id'],
        bidder=bidder,
        amount_cents=amount_cents,
        bid_count=lot['bid_count'] + 1,
        at=at,
        ends_at=ends_at,
        previous_ends_at=previous_ends_at,
        outbid_user_id=outbid_user_id,
    )
    return result, event


async def _find_bid_by_key(ctx: AppContext, db: Queryable, user_id: str, key: str) -> PlaceBidResult | None:
    res = await db.query(
        'SELECT id, lot_id, amount_cents, created_at FROM bids WHERE user_id = $1 AND idempotency_key = $2',
        [user_id, key],
    )
    if not res.rows:
        return None
    bid = res.rows[0]
    return PlaceBidResult(
        bid_id=bid['id'],
        lot_id=bid['lot_id'],
        amount_cents=bid['amount_cents'],
        bidder=bidder_pseudonym(ctx.pseudonym_secret, user_id, bid['lot_id']),
        at=iso(bid['created_at']),
        replayed=True,
    )


# ---------------------------------------------------------------- cancelamento (spec 002, US4)


async def cancel_lot(ctx: AppContext, *, auctioneer_id: str, lot_id: str) -> dict[str, str]:
    """Cancela um lote do leiloeiro ainda não encerrado e sem lances (FR-015, FR-016 da 002).
    Disputa o mesmo `FOR UPDATE` do lance: um lance e um cancelamento simultâneos nunca são
    os dois aceitos. Lote de outro dono responde como inexistente (D-08 da 002)."""

    async def run(tx: Tx) -> LotCancelledEvent:
        res = await tx.query(f'SELECT {LOCKED_LOT_COLUMNS} FROM lots WHERE id = $1 FOR UPDATE', [lot_id])
        lot = res.rows[0] if res.rows else None
        if not lot or lot['auctioneer_id'] != auctioneer_id:
            raise AppError('NOT_FOUND', 'Lote não encontrado')

        clock = await _lot_clock(tx, lot['id'])
        if lot['status'] != 'open' or clock['ended']:
            raise AppError('LOT_NOT_CANCELLABLE', 'Só é possível cancelar lote que ainda não encerrou')
        if lot['bid_count'] > 0:
            raise AppError('LOT_HAS_BIDS', 'O lote já recebeu lances')

        updated = await tx.query(
            "UPDATE lots SET status = 'cancelled', cancelled_at = $2 WHERE id = $1 RETURNING cancelled_at",
            [lot['id'], clock['now']],
        )
        at = iso(updated.rows[0]['cancelled_at'])
        await append_audit_event(tx, ctx.signer, lot, 'lot_cancelled', {'at': at}, ctx.witness)
        return LotCancelledEvent(lot_id=lot['id'], at=at)

    event = await with_tx(ctx.db, run)
    await ctx.events.emit('lot:cancelled', event)  # só após COMMIT
    return {'id': event.lot_id, 'status': 'cancelled', 'cancelled_at': event.at}


# ---------------------------------------------------------------- liquidação (P3)


async def settle_lot(ctx: AppContext, lot_id: str) -> LotSettledEvent | None:
    """Liquida um lote vencido, se houver. Idempotente: segunda chamada é no-op."""

    async def run(tx: Tx) -> LotSettledEvent | None:
        res = await tx.query(f'SELECT {LOCKED_LOT_COLUMNS} FROM lots WHERE id = $1 FOR UPDATE', [lot_id])
        return await _settle_locked_lot(ctx, tx, res.rows[0]) if res.rows else None

    event = await with_tx(ctx.db, run)
    if event:
        await ctx.events.emit('lot:settled', event)
    return event


_EMPTY = object()


async def settle_due_lots(ctx: AppContext, max_lots: int = 100) -> int:
    """Job periódico: um lote por transação, com SKIP LOCKED para que várias instâncias (ou
    lances em andamento) não bloqueiem o job."""
    settled = 0

    async def run(tx: Tx) -> object:
        res = await tx.query(
            f"""SELECT {LOCKED_LOT_COLUMNS} FROM lots
          WHERE status = 'open' AND ends_at <= clock_timestamp()
          ORDER BY ends_at LIMIT 1 FOR UPDATE SKIP LOCKED"""
        )
        if not res.rows:
            return _EMPTY
        return await _settle_locked_lot(ctx, tx, res.rows[0])

    for _ in range(max_lots):
        outcome = await with_tx(ctx.db, run)
        if outcome is _EMPTY:
            break
        if isinstance(outcome, LotSettledEvent):
            settled += 1
            await ctx.events.emit('lot:settled', outcome)
    return settled


async def _settle_locked_lot(ctx: AppContext, tx: Tx, lot: Row) -> LotSettledEvent | None:
    if lot['status'] != 'open':
        return None
    clock = await _lot_clock(tx, lot['id'])
    if not clock['ended']:
        return None

    winner: str | None = None
    if lot['leader_user_id'] and lot['current_price_cents'] is not None:
        await tx.query('SELECT 1 FROM wallets WHERE user_id = $1 FOR UPDATE', [lot['leader_user_id']])
        await tx.query(
            'UPDATE wallets SET balance_cents = balance_cents - $2, updated_at = clock_timestamp() WHERE user_id = $1',
            [lot['leader_user_id'], lot['current_price_cents']],
        )
        await tx.query(
            "INSERT INTO ledger_entries (user_id, kind, amount_cents, lot_id) VALUES ($1, 'settlement_debit', $2, $3)",
            [lot['leader_user_id'], -lot['current_price_cents'], lot['id']],
        )
        # Crédito ao leiloeiro no mesmo ato (FR-019 da 002). Ordem lote → carteira do vencedor →
        # carteira do leiloeiro: sem ciclo, porque leiloeiro nunca vence (ADR spec002).
        await tx.query('SELECT 1 FROM wallets WHERE user_id = $1 FOR UPDATE', [lot['auctioneer_id']])
        credited = await tx.query(
            'UPDATE wallets SET balance_cents = balance_cents + $2, updated_at = clock_timestamp() WHERE user_id = $1',
            [lot['auctioneer_id'], lot['current_price_cents']],
        )
        if credited.rowcount != 1:
            raise RuntimeError(f'carteira do leiloeiro ausente (lote {lot["id"]})')
        await tx.query(
            "INSERT INTO ledger_entries (user_id, kind, amount_cents, lot_id) VALUES ($1, 'settlement_credit', $2, $3)",
            [lot['auctioneer_id'], lot['current_price_cents'], lot['id']],
        )
        winner = bidder_pseudonym(ctx.pseudonym_secret, lot['leader_user_id'], lot['id'])

    status: Literal['settled', 'unsold'] = 'settled' if winner else 'unsold'
    res = await tx.query(
        'UPDATE lots SET status = $2, settled_at = $3 WHERE id = $1 RETURNING settled_at',
        [lot['id'], status, clock['now']],
    )
    at = iso(res.rows[0]['settled_at'])
    await append_audit_event(
        tx,
        ctx.signer,
        lot,
        'lot_settled' if winner else 'lot_unsold',
        {'winner': winner, 'final_price_cents': lot['current_price_cents'], 'bid_count': lot['bid_count'], 'at': at},
        ctx.witness,
    )
    return LotSettledEvent(
        lot_id=lot['id'],
        status=status,
        winner=winner,
        final_price_cents=lot['current_price_cents'],
        at=at,
        winner_user_id=lot['leader_user_id'],
    )


def start_settlement_scheduler(
    ctx: AppContext, interval_ms: int, on_error: Callable[[BaseException], None]
) -> Callable[[], None]:
    """Roda `settle_due_lots` a cada `interval_ms`. Uma rodada nunca se sobrepõe à anterior."""

    async def loop() -> None:
        while True:
            await asyncio.sleep(interval_ms / 1000)
            try:
                await settle_due_lots(ctx)
            except Exception as err:
                on_error(err)

    task = asyncio.get_running_loop().create_task(loop())
    return task.cancel  # type: ignore[return-value]


# ---------------------------------------------------------------- leitura

LotPhase = Literal['scheduled', 'live', 'ended', 'cancelled']

# Fase do lote derivada do relógio do banco (spec 003, D-01). Usa `l` (lotes) e `c.now`
# (clock_timestamp()). Compartilhada pela vitrine, pela sala e pelo painel.
PHASE_SQL = """CASE WHEN l.status = 'cancelled' THEN 'cancelled'
            WHEN l.status <> 'open' OR c.now >= l.ends_at THEN 'ended'
            WHEN c.now < l.starts_at THEN 'scheduled'
            ELSE 'live' END"""


def _image_url(path: str | None) -> str | None:
    return f'/images/{path}' if path else None


def _to_public_lot(ctx: AppContext, row: Row, viewer_id: str | None = None) -> dict[str, Any]:
    status = row['status']
    return {
        'id': row['id'],
        'item': {
            'id': row['item_id'],
            'title': row['title'],
            'description': row['description'],
            'image_url': _image_url(row['image_path']),
            'size': row['size'],
            'condition': row['condition'],
            'attributes': row['attributes'],
        },
        'status': status,
        'phase': row['phase'],
        # Mesmo conceito do `outcome` do painel da 002, só para lotes encerrados.
        'result': 'sold' if status == 'settled' else 'unsold' if status == 'unsold' else None,
        'starting_price_cents': row['starting_price_cents'],
        'min_increment_cents': row['min_increment_cents'],
        'current_price_cents': row['current_price_cents'],
        'next_minimum_cents': row['starting_price_cents']
        if row['current_price_cents'] is None
        else row['current_price_cents'] + row['min_increment_cents'],
        'leader': bidder_pseudonym(ctx.pseudonym_secret, row['leader_user_id'], row['id'])
        if row['leader_user_id']
        else None,
        'you_are_leading': viewer_id is not None and row['leader_user_id'] == viewer_id,
        'bid_count': row['bid_count'],
        'starts_at': iso(row['starts_at']),
        'ends_at': iso(row['ends_at']),
        'original_ends_at': iso(row['original_ends_at']),
        'extended': row['extended'],
        'settled_at': iso_or_none(row['settled_at']),
        'audit_head_hash': row['audit_head_hash'],
    }


# Título e imagem vêm da cópia do lote (D-09 da 002), não do item do catálogo.
LOT_SELECT = f"""SELECT l.*, i.description, {PHASE_SQL} AS phase, l.ends_at > l.original_ends_at AS extended
  FROM lots l JOIN items i ON i.id = l.item_id, LATERAL (SELECT clock_timestamp() AS now) c"""


async def settle_due(ctx: AppContext, filter_sql: str, params: list[Any]) -> None:
    """Liquidação preguiçosa (Const. 3.3) dos lotes vencidos e ainda abertos."""
    due = await ctx.db.query(
        f"SELECT id FROM lots WHERE status = 'open' AND ends_at <= clock_timestamp() {filter_sql}", params
    )
    for row in due.rows:
        await settle_lot(ctx, row['id'])


async def list_lots(ctx: AppContext, viewer_id: str | None = None) -> list[dict[str, Any]]:
    """Vitrine (FR-020, FR-021 da 003): nunca lista cancelados. Ordem (D-14): ao vivo pelo fim mais
    próximo, agendados pelo início mais próximo, encerrados pelo fim mais recente."""
    await settle_due(ctx, '', [])
    res = await ctx.db.query(
        f"""SELECT * FROM ({LOT_SELECT} WHERE l.status <> 'cancelled') x
      ORDER BY CASE phase WHEN 'live' THEN 0 WHEN 'scheduled' THEN 1 ELSE 2 END,
               CASE WHEN phase = 'live' THEN ends_at END ASC,
               CASE WHEN phase = 'scheduled' THEN starts_at END ASC,
               CASE WHEN phase = 'ended' THEN ends_at END DESC""",
        [],
    )
    return [_to_public_lot(ctx, r, viewer_id) for r in res.rows]


async def get_lot(ctx: AppContext, lot_id: str, viewer_id: str | None = None) -> dict[str, Any]:
    exists = await ctx.db.query('SELECT 1 FROM lots WHERE id = $1', [lot_id])
    if not exists.rowcount:
        raise AppError('NOT_FOUND', 'Lote não encontrado')
    # Liquidação preguiçosa (RB9): quem lê um lote vencido já o vê encerrado.
    await settle_due(ctx, 'AND id = $1', [lot_id])
    res = await ctx.db.query(f'{LOT_SELECT} WHERE l.id = $1', [lot_id])
    lot = _to_public_lot(ctx, res.rows[0], viewer_id)

    bids = await ctx.db.query(
        'SELECT id, user_id, amount_cents, created_at FROM bids WHERE lot_id = $1 ORDER BY id DESC LIMIT 50', [lot_id]
    )
    # Posição derivada (FR-011 da 003): maior lance de cada licitante; empate vai para quem chegou antes.
    ranking = await ctx.db.query(
        """SELECT user_id, max(amount_cents)::bigint AS max_cents FROM bids WHERE lot_id = $1
      GROUP BY user_id ORDER BY max(amount_cents) DESC, min(id)""",
        [lot_id],
    )

    def pseudonym(user_id: str) -> str:
        return bidder_pseudonym(ctx.pseudonym_secret, user_id, lot_id)

    standings = [{'bidder': pseudonym(r['user_id']), 'max_cents': r['max_cents']} for r in ranking.rows]

    out: dict[str, Any] = {**lot, 'standings': standings}
    if viewer_id:
        # Só o próprio usuário recebe o próprio pseudônimo: marca "você" sem expor ninguém (Art. 5).
        index = next((i for i, r in enumerate(ranking.rows) if r['user_id'] == viewer_id), -1)
        out['viewer'] = {
            'bidder': pseudonym(viewer_id),
            'has_bid': index >= 0,
            'position': index + 1 if index >= 0 else None,
            'total_bidders': len(ranking.rows),
            'leading': lot['you_are_leading'],
        }
    out['bids'] = [
        {
            'id': b['id'],
            'bidder': pseudonym(b['user_id']),
            'amount_cents': b['amount_cents'],
            'at': iso(b['created_at']),
        }
        for b in bids.rows
    ]
    return out


# ---------------------------------------------------------------- painel do leiloeiro (spec 002, US5)


async def list_auctioneer_lots(ctx: AppContext, auctioneer_id: str) -> dict[str, Any]:
    """Lotes do próprio leiloeiro com o resultado de cada um e o total recebido (FR-005, FR-017,
    FR-018 da 002). Vencidos ainda abertos são liquidados antes (D-13)."""
    await settle_due(ctx, 'AND auctioneer_id = $1', [auctioneer_id])

    res = await ctx.db.query(
        f"""SELECT l.id, l.title, l.image_path, l.size, l.condition, l.attributes, l.status,
            l.starting_price_cents, l.min_increment_cents, l.current_price_cents, l.bid_count,
            l.starts_at, l.ends_at, l.settled_at, l.cancelled_at, l.created_at,
            {PHASE_SQL} AS phase
       FROM lots l, LATERAL (SELECT clock_timestamp() AS now) c
      WHERE l.auctioneer_id = $1
      ORDER BY l.created_at DESC""",
        [auctioneer_id],
    )
    total = await ctx.db.query(
        """SELECT COALESCE(SUM(amount_cents), 0)::bigint AS total
       FROM ledger_entries WHERE user_id = $1 AND kind = 'settlement_credit'""",
        [auctioneer_id],
    )

    def outcome_of(status: str) -> str:
        return {'settled': 'sold', 'unsold': 'unsold', 'cancelled': 'cancelled'}.get(status, 'open')

    return {
        'total_received_cents': total.rows[0]['total'],
        'lots': [
            {
                'id': r['id'],
                'title': r['title'],
                'image_url': _image_url(r['image_path']),
                'size': r['size'],
                'condition': r['condition'],
                'attributes': r['attributes'],
                'phase': r['phase'],
                'outcome': outcome_of(r['status']),
                'starting_price_cents': r['starting_price_cents'],
                'min_increment_cents': r['min_increment_cents'],
                'current_price_cents': r['current_price_cents'],
                'final_price_cents': r['current_price_cents'] if r['status'] == 'settled' else None,
                'bid_count': r['bid_count'],
                'can_cancel': r['status'] == 'open' and r['phase'] != 'ended' and r['bid_count'] == 0,
                'starts_at': iso(r['starts_at']),
                'ends_at': iso(r['ends_at']),
                'settled_at': iso_or_none(r['settled_at']),
                'cancelled_at': iso_or_none(r['cancelled_at']),
            }
            for r in res.rows
        ],
    }
