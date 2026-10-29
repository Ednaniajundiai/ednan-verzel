import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { formatBRL } from '../../lib/money';
import { useSocketStatus } from '../../lib/socket';
import { useEffect, useRef, useState } from 'react';
import { BidForm } from './BidForm';
import { BidHistory } from './BidHistory';
import { Countdown } from './Countdown';
import { LeadIndicator } from './LeadIndicator';
import { ResultPanel } from './ResultPanel';
import { StandingBanner } from './StandingBanner';
import { useLotRoom } from './useLotRoom';

const PHASE_LABEL = { scheduled: 'Agendado', live: 'Ao vivo', ended: 'Encerrado', cancelled: 'Cancelado' } as const;
const time = (iso: string) => new Date(iso).toLocaleTimeString('pt-BR');

/** "Reconectando…" só depois de ter estado conectado (FR-017). */
function useReconnecting(): boolean {
  const status = useSocketStatus();
  const wasConnected = useRef(status === 'connected');
  const [reconnecting, setReconnecting] = useState(false);
  useEffect(() => {
    if (status === 'connected') {
      wasConnected.current = true;
      setReconnecting(false);
    } else if (wasConnected.current) {
      setReconnecting(true);
    }
  }, [status]);
  return reconnecting;
}

/** Sala do lote (spec 003, H2 e H3): tudo atualizado sem recarregar a página. */
export function SalaPage() {
  const { id = '' } = useParams();
  const { user } = useAuth();
  const { lot, error, extendedAt, reload, confirmPhase } = useLotRoom(id);
  const reconnecting = useReconnecting();

  if (!lot) {
    return error ? (
      <p className="notice error" role="alert">
        {error}
      </p>
    ) : (
      <p className="muted">Carregando…</p>
    );
  }

  const viewer = lot.viewer;
  const isBidder = user?.role === 'bidder';
  const attrs = [lot.item.attributes.team, lot.item.attributes.season, lot.item.size, lot.item.condition?.replaceAll('_', ' ')]
    .filter(Boolean)
    .join(' · ');

  return (
    <section className="sala">
      {reconnecting && (
        <p className="notice warning" role="status">
          Reconectando…
        </p>
      )}
      <div className="sala-grid">
        <div className="stack">
          {lot.item.image_url && <img className="sala-image" src={lot.item.image_url} alt={lot.item.title} />}
          <div>
            <span className={`badge phase-${lot.phase}`}>{PHASE_LABEL[lot.phase]}</span>
            <h1>{lot.item.title}</h1>
            {attrs && <p className="muted">{attrs}</p>}
          </div>
        </div>

        <div className="stack">
          {lot.phase === 'cancelled' && (
            <div className="card stack">
              <strong>Lote cancelado</strong>
              <p className="muted">O leiloeiro cancelou este lote antes de qualquer lance.</p>
            </div>
          )}

          {lot.phase === 'scheduled' && (
            <div className="card stack">
              <p>
                Começa em <Countdown target={lot.starts_at} onZero={confirmPhase} />
              </p>
              <p>{`Lance inicial: ${formatBRL(lot.starting_price_cents)}`}</p>
              <p>{`Incremento mínimo: ${formatBRL(lot.min_increment_cents)}`}</p>
            </div>
          )}

          {lot.phase === 'live' && (
            <div className="card stack">
              <div className="price" data-testid="current-price">
                <span className="muted">{lot.current_price_cents === null ? 'Lance inicial' : 'Lance atual'}</span>
                <strong>{formatBRL(lot.current_price_cents ?? lot.starting_price_cents)}</strong>
              </div>
              <p data-testid="next-minimum">{`Próximo lance mínimo: ${formatBRL(lot.next_minimum_cents)}`}</p>
              <p>
                Termina em <Countdown target={lot.ends_at} onZero={confirmPhase} />
              </p>
              {extendedAt && <p className="notice warning">{`Lote prorrogado: novo fim às ${time(extendedAt)}.`}</p>}
            </div>
          )}

          {lot.phase === 'ended' && <ResultPanel lot={lot} />}

          {viewer && isBidder && lot.phase !== 'cancelled' && (
            <div className="card stack">
              {viewer.has_bid && lot.phase !== 'ended' && <LeadIndicator leading={viewer.leading} />}
              <StandingBanner position={viewer.position} total={viewer.total_bidders} />
            </div>
          )}

          {(lot.phase === 'live' || lot.phase === 'scheduled') && (
            <div className="card">
              {isBidder ? (
                <BidForm lotId={lot.id} minimumCents={lot.next_minimum_cents} disabled={lot.phase !== 'live'} onPlaced={reload} />
              ) : user?.role === 'auctioneer' ? (
                <p className="muted">Leiloeiros não dão lances. Você está acompanhando a sala.</p>
              ) : (
                <p>
                  <Link to="/entrar">Entre para dar lance</Link>
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="card stack">
        <h2>Histórico de lances</h2>
        <BidHistory bids={lot.bids} me={viewer?.bidder} />
        <p className="muted">
          Licitantes aparecem por pseudônimo, diferente em cada lote. <Link to={`/auditoria/${lot.id}`}>Auditar este lote</Link>
        </p>
      </div>
    </section>
  );
}
