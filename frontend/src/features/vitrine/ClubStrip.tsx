import { useState } from 'react';
import { CLUBS, type ClubGroup } from '../lots/clubs';
import { ClubCrest } from './ClubCrest';

const GROUPS: { group: ClubGroup; tab: string; list: string }[] = [
  { group: 'serie_a', tab: 'Série A', list: 'Clubes da Série A' },
  { group: 'internacional', tab: 'Internacionais', list: 'Clubes internacionais' },
];

/**
 * Faixa de escudos (spec 006): um clique filtra, outro clique no mesmo escudo desfaz. Mostra
 * quantas camisas cada clube tem (como as categorias do Superbid); clube sem camisa fica apagado.
 */
export function ClubStrip({
  selected,
  onSelect,
  counts,
}: {
  selected: string | null;
  onSelect: (code: string | null) => void;
  counts: Map<string, number> | null;
}) {
  const [group, setGroup] = useState<ClubGroup>(() => CLUBS.find((c) => c.code === selected)?.group ?? 'serie_a');
  const current = GROUPS.find((g) => g.group === group)!;

  return (
    <section className="club-strip" aria-label="Filtrar por clube">
      <div className="club-strip-head">
        <h2 className="club-strip-title">Escolha o clube</h2>
        <div className="tabs" role="tablist">
          {GROUPS.map((g) => (
            <button
              key={g.group}
              type="button"
              role="tab"
              aria-selected={g.group === group}
              onClick={() => setGroup(g.group)}
            >
              {g.tab}
            </button>
          ))}
        </div>
      </div>
      <div className="club-row">
        <button
          type="button"
          className="club-chip club-all"
          aria-pressed={selected === null}
          onClick={() => onSelect(null)}
        >
          <svg className="crest" width="40" height="40" viewBox="0 0 40 40" aria-hidden="true">
            <circle cx="20" cy="20" r="17" fill="none" stroke="currentColor" strokeWidth="2.5" />
            <path d="M20 12 L27 17 L24.5 25 H15.5 L13 17 Z" fill="currentColor" />
            <path d="M20 3 V12 M27 17 L36 14 M24.5 25 L30 33 M15.5 25 L10 33 M13 17 L4 14" stroke="currentColor" strokeWidth="2" />
          </svg>
          <span>Todos os clubes</span>
        </button>
        <ul className="club-list" aria-label={current.list}>
          {CLUBS.filter((c) => c.group === group).map((c) => {
            const count = counts?.get(c.code) ?? 0;
            return (
              <li key={c.code}>
                <button
                  type="button"
                  className={counts && count === 0 ? 'club-chip is-empty' : 'club-chip'}
                  aria-pressed={selected === c.code}
                  title={`${c.name} · ${count === 1 ? '1 camisa' : `${count} camisas`}`}
                  onClick={() => onSelect(selected === c.code ? null : c.code)}
                >
                  {count > 0 && (
                    <span className="club-count" aria-hidden="true">
                      {count}
                    </span>
                  )}
                  <ClubCrest club={c} />
                  <span>{c.name}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
