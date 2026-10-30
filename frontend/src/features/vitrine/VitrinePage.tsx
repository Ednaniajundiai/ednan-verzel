import { useState } from 'react';
import { filterLots, type PhaseFilter } from '../lots/filter';
import type { PublicLot } from '../lots/types';
import { ClubStrip } from './ClubStrip';
import { clubCounts, endingSoon, featuredLot, highestBids, mostDisputed } from './highlights';
import { LiveTicker } from './LiveTicker';
import { LotCard } from './LotCard';
import { LotRow } from './LotRow';
import { Scoreboard } from './Scoreboard';
import { SearchBar } from './SearchBar';
import { useLots } from './useLots';

const SECTIONS = [
  { phase: 'live', title: 'Ao vivo', empty: 'Nenhum lote ao vivo agora' },
  { phase: 'scheduled', title: 'Agendados', empty: 'Nenhum lote agendado' },
  { phase: 'ended', title: 'Encerrados', empty: 'Nenhum lote encerrado' },
] as const;

/**
 * Vitrine (spec 003): três seções, nunca cancelados, tudo ao vivo; filtro por escudo (spec 006).
 * Home em "placar ao vivo": faixa ao vivo, lote em destaque e fileiras temáticas, que saem
 * de cena enquanto há filtro para a busca mostrar só o resultado.
 */
export function VitrinePage() {
  const { lots, error } = useLots();
  const [query, setQuery] = useState('');
  const [phase, setPhase] = useState<PhaseFilter>('all');
  const [club, setClub] = useState<string | null>(null);

  const visible = lots ? filterLots(lots, query, phase, club) : [];
  const searching = query.trim() !== '';
  const browsing = !searching && !club && phase === 'all';
  const clubIsEmpty = lots !== null && club !== null && filterLots(lots, '', 'all', club).length === 0;
  const featured = lots ? featuredLot(lots) : null;

  return (
    <section className="stack vitrine">
      <div className="page-intro">
        <h1>Camisas antigas e raras do time Verzel</h1>
        <p className="muted">Colaboradores anunciam, você dá o lance ao vivo.</p>
      </div>
      {lots && <LiveTicker lots={endingSoon(lots).filter((l) => l.phase === 'live')} />}
      {featured && <Scoreboard lot={featured} />}

      <ClubStrip selected={club} onSelect={setClub} counts={lots ? clubCounts(lots) : null} />
      <SearchBar query={query} phase={phase} onQuery={setQuery} onPhase={setPhase} />
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {!lots && !error && <p className="muted">Carregando…</p>}

      {lots && browsing && (
        <>
          <LotRow id="terminando" title="Terminando em breve" lots={endingSoon(lots)} />
          <LotRow id="disputadas" title="Mais disputadas" lots={mostDisputed(lots)} />
          <LotRow id="maiores" title="Maiores lances" lots={highestBids(lots)} />
        </>
      )}

      <section className="stack catalog" aria-label="Todas as camisas">
        {clubIsEmpty ? (
          <div className="empty-state stack">
            <p>Nenhuma camisa deste clube no momento</p>
            <div>
              <button type="button" onClick={() => setClub(null)}>
                Ver todos os clubes
              </button>
            </div>
          </div>
        ) : lots && searching && visible.length === 0 ? (
          <div className="empty-state stack">
            <p>Nenhum lote encontrado</p>
            <div>
              <button type="button" onClick={() => setQuery('')}>
                Limpar busca
              </button>
            </div>
          </div>
        ) : (
          lots &&
          SECTIONS.filter((s) => phase === 'all' || phase === s.phase).map((s) => {
            const items: PublicLot[] = visible.filter((l) => l.phase === s.phase);
            return (
              <section key={s.phase} aria-labelledby={`sec-${s.phase}`} className={`stack lot-section sec-${s.phase}`}>
                <h2 id={`sec-${s.phase}`}>{s.title}</h2>
                {items.length === 0 ? (
                  <p className="muted">{s.empty}</p>
                ) : (
                  <div className="grid">
                    {items.map((l) => (
                      <LotCard key={l.id} lot={l} />
                    ))}
                  </div>
                )}
              </section>
            );
          })
        )}
      </section>
    </section>
  );
}
