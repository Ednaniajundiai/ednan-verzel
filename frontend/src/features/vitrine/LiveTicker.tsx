import { Link } from 'react-router-dom';
import { formatBRL } from '../../lib/money';
import { clubOf } from '../lots/clubs';
import type { PublicLot } from '../lots/types';
import { Countdown } from '../sala/Countdown';
import { ClubCrest } from './ClubCrest';

function TickerItems({ lots, copy = false }: { lots: PublicLot[]; copy?: boolean }) {
  return (
    <>
      {lots.map((l) => {
        const club = clubOf(l.item.attributes.team);
        return (
          <Link key={l.id} to={`/lotes/${l.id}`} className="ticker-item" tabIndex={copy ? -1 : undefined}>
            {club && <ClubCrest club={club} size={22} />}
            <span className="ticker-title">{l.item.title}</span>
            <strong>{formatBRL(l.current_price_cents ?? l.starting_price_cents)}</strong>
            <Countdown target={l.ends_at} />
          </Link>
        );
      })}
    </>
  );
}

/** Faixa "ao vivo" no topo (ideia 2, inspirada no Superbid): some quando nada está ao vivo. */
export function LiveTicker({ lots }: { lots: PublicLot[] }) {
  if (lots.length === 0) return null;
  return (
    <section className="ticker" aria-label="Lotes ao vivo agora">
      <span className="ticker-label">
        <span className="live-dot" aria-hidden="true" />
        Ao vivo
      </span>
      <div className="ticker-viewport">
        <div className="ticker-track">
          <TickerItems lots={lots} />
          {/* Cópia só para o giro emendar sem salto; leitores de tela leem uma vez. */}
          <div className="ticker-copy" aria-hidden="true">
            <TickerItems lots={lots} copy />
          </div>
        </div>
      </div>
    </section>
  );
}
