import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { formatBRL } from '../../lib/money';
import { clubOf } from '../lots/clubs';
import type { PublicLot } from '../lots/types';
import { Countdown } from '../sala/Countdown';
import { ClubCrest } from './ClubCrest';

const KICKER = { live: 'Ao vivo agora', scheduled: 'Próximo lote', ended: 'Último resultado', cancelled: '' } as const;
const dateTime = (iso: string) =>
  new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

function Cell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="score-cell">
      <span>{label}</span>
      <strong>{children}</strong>
    </div>
  );
}

/** "Jogo da rodada" (ideia 2): o lote em destaque como um placar. */
export function Scoreboard({ lot }: { lot: PublicLot }) {
  const club = clubOf(lot.item.attributes.team);
  const { season } = lot.item.attributes;

  return (
    <section className={`scoreboard phase-${lot.phase}`} aria-labelledby="destaque-title">
      <svg className="pitch" viewBox="0 0 400 260" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <rect x="10" y="10" width="380" height="240" fill="none" />
        <line x1="200" y1="10" x2="200" y2="250" />
        <circle cx="200" cy="130" r="42" fill="none" />
        <circle cx="200" cy="130" r="3" />
        <rect x="10" y="70" width="58" height="120" fill="none" />
        <rect x="332" y="70" width="58" height="120" fill="none" />
      </svg>
      <div className="score-shapes" aria-hidden="true">
        <span className="tri tri-violet" />
        <span className="tri tri-cyan" />
        <span className="tri tri-lime" />
      </div>

      <div className="score-media">
        {lot.item.image_url ? <img src={lot.item.image_url} alt="" /> : <span className="placeholder-img">Sem imagem</span>}
      </div>

      <div className="score-body">
        <h2 id="destaque-title" className="score-kicker">
          {lot.phase === 'live' && <span className="live-dot" aria-hidden="true" />}
          Destaque da rodada · {KICKER[lot.phase]}
        </h2>
        <div className="score-team">
          {club && <ClubCrest club={club} size={44} />}
          <div>
            <p className="score-club">{club?.name ?? lot.item.attributes.team ?? 'Camisa'}</p>
            {season && <p className="score-season">Temporada {season}</p>}
          </div>
        </div>
        <p className="score-title">{lot.item.title}</p>

        <div className="score-panel">
          {lot.phase === 'live' && (
            <>
              <Cell label={lot.current_price_cents === null ? 'Lance inicial' : 'Lance atual'}>
                {formatBRL(lot.current_price_cents ?? lot.starting_price_cents)}
              </Cell>
              <Cell label="Lances">{lot.bid_count}</Cell>
              <Cell label="Termina em">
                <Countdown target={lot.ends_at} />
              </Cell>
            </>
          )}
          {lot.phase === 'scheduled' && (
            <>
              <Cell label="Lance inicial">{formatBRL(lot.starting_price_cents)}</Cell>
              <Cell label="Incremento">{formatBRL(lot.min_increment_cents)}</Cell>
              <Cell label="Começa em">
                <Countdown target={lot.starts_at} />
              </Cell>
            </>
          )}
          {lot.phase === 'ended' && (
            <>
              <Cell label={lot.result === 'sold' ? 'Arrematado por' : 'Resultado'}>
                {lot.result === 'sold' ? formatBRL(lot.current_price_cents ?? 0) : 'Sem vencedor'}
              </Cell>
              <Cell label="Lances">{lot.bid_count}</Cell>
              <Cell label="Encerrado">{dateTime(lot.settled_at ?? lot.ends_at)}</Cell>
            </>
          )}
        </div>

        <div>
          <Link to={`/lotes/${lot.id}`} className="score-cta">
            {lot.phase === 'live' ? 'Entrar na sala' : 'Ver lote'}
          </Link>
        </div>
      </div>
    </section>
  );
}
