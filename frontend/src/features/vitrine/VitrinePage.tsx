import { useState } from 'react';
import { filterLots, type PhaseFilter } from '../lots/filter';
import type { PublicLot } from '../lots/types';
import { LotCard } from './LotCard';
import { SearchBar } from './SearchBar';
import { useLots } from './useLots';

const SECTIONS = [
  { phase: 'live', title: 'Ao vivo', empty: 'Nenhum lote ao vivo agora' },
  { phase: 'scheduled', title: 'Agendados', empty: 'Nenhum lote agendado' },
  { phase: 'ended', title: 'Encerrados', empty: 'Nenhum lote encerrado' },
] as const;

/** Vitrine (spec 003): três seções, nunca cancelados, tudo ao vivo. */
export function VitrinePage() {
  const { lots, error } = useLots();
  const [query, setQuery] = useState('');
  const [phase, setPhase] = useState<PhaseFilter>('all');

  const visible = lots ? filterLots(lots, query, phase) : [];
  const searching = query.trim() !== '';

  return (
    <section className="stack">
      <div className="page-head">
        <h1>Camisas de futebol em leilão</h1>
      </div>
      <SearchBar query={query} phase={phase} onQuery={setQuery} onPhase={setPhase} />
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {!lots && !error && <p className="muted">Carregando…</p>}
      {lots && searching && visible.length === 0 ? (
        <div className="stack">
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
            <section key={s.phase} aria-labelledby={`sec-${s.phase}`} className="stack">
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
  );
}
