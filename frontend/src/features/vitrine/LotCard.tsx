import { Link } from 'react-router-dom';
import { formatBRL } from '../../lib/money';
import { clubOf } from '../lots/clubs';
import type { PublicLot } from '../lots/types';
import { Countdown } from '../sala/Countdown';
import { ClubCrest } from './ClubCrest';

/** Cartão com a informação própria da fase (FR-021) e o escudo do clube (spec 006). */
export function LotCard({ lot }: { lot: PublicLot }) {
  const club = clubOf(lot.item.attributes.team);
  return (
    <article className={`card lot-card stack phase-${lot.phase}`}>
      {lot.item.image_url ? (
        <img className="thumb" src={lot.item.image_url} alt="" loading="lazy" />
      ) : (
        <span className="placeholder-img">Sem imagem</span>
      )}
      <div className="lot-title">
        {club && <ClubCrest club={club} size={32} label={`Escudo do ${club.name}`} />}
        <h3>
          <Link to={`/lotes/${lot.id}`}>{lot.item.title}</Link>
        </h3>
      </div>
      {lot.phase === 'live' && (
        <>
          <p>
            {lot.current_price_cents === null
              ? `Lance inicial: ${formatBRL(lot.starting_price_cents)}`
              : `Lance atual: ${formatBRL(lot.current_price_cents)}`}
          </p>
          <p className="muted">
            Termina em <Countdown target={lot.ends_at} />
          </p>
        </>
      )}
      {lot.phase === 'scheduled' && (
        <>
          <p>{`Lance inicial: ${formatBRL(lot.starting_price_cents)}`}</p>
          <p className="muted">
            Começa em <Countdown target={lot.starts_at} />
          </p>
        </>
      )}
      {lot.phase === 'ended' && (
        <p>{lot.result === 'sold' ? `Arrematado por ${formatBRL(lot.current_price_cents ?? 0)}` : 'Sem vencedor'}</p>
      )}
    </article>
  );
}
