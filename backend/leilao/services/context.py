import inspect
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from leilao.db import Db

if TYPE_CHECKING:
    from leilao.services.audit import AuditSigner
    from leilao.services.thesportsdb import TheSportsDbClient
    from leilao.services.witness import WitnessLog

log = logging.getLogger('leilao.events')


@dataclass
class BidPlacedEvent:
    lot_id: str
    bid_id: int
    bidder: str
    amount_cents: int
    bid_count: int
    at: str
    # Fim vigente depois do lance (ISO com µs).
    ends_at: str
    # Interno: usado para avisar o usuário superado na sala privada; nunca vai para a sala pública.
    outbid_user_id: str | None
    # Presente só quando o lance prorrogou o lote.
    previous_ends_at: str | None = None


@dataclass
class LotSettledEvent:
    lot_id: str
    status: Literal['settled', 'unsold']
    winner: str | None
    final_price_cents: int | None
    at: str
    winner_user_id: str | None


@dataclass
class LotCancelledEvent:
    lot_id: str
    at: str


@dataclass
class WalletChangedEvent:
    user_id: str
    balance_cents: int
    committed_cents: int
    available_cents: int


EventName = Literal['bid:placed', 'lot:settled', 'lot:cancelled', 'wallet:changed']
Handler = Callable[[Any], Any]


class EventBus:
    """Eventos de domínio (o `EventEmitter` do Node). `emit` é chamado só depois do COMMIT e
    aguarda os ouvintes em ordem: `bid:placed` sai antes de `lot:extended` e de `bid:outbid`."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def on(self, name: EventName, handler: Handler) -> None:
        self._handlers[name].append(handler)

    def remove_all_listeners(self) -> None:
        self._handlers.clear()

    async def emit(self, name: EventName, event: Any) -> None:
        for handler in list(self._handlers[name]):
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                log.exception('[events] ouvinte de %s falhou', name)


@dataclass
class LotRules:
    """Prorrogação anti-sniping (spec 003): lance aceito com `extension_window_ms` ou menos para o
    fim leva o fim a `instante do lance + extension_ms`. Em ms para os testes; em produção, 2 min."""

    extension_window_ms: int = 120_000
    extension_ms: int = 120_000


def default_rules() -> LotRules:
    return LotRules()


@dataclass
class CatalogDeps:
    """Catálogo de camisas (D-03 da 002): cliente da fonte externa + onde guardar as cópias."""

    client: 'TheSportsDbClient'
    storage_dir: Path
    ttl_hours: float


@dataclass
class AppContext:
    db: Db
    signer: 'AuditSigner'
    pseudonym_secret: str
    # Segredo do token do link público do comprovante (spec 004, S-07).
    receipt_secret: str
    catalog: CatalogDeps
    # Testemunha da trilha fora do banco (spec 004).
    witness: 'WitnessLog'
    events: EventBus = field(default_factory=EventBus)
    rules: LotRules = field(default_factory=default_rules)
