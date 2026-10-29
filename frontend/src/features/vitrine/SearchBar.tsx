import type { PhaseFilter } from '../lots/filter';

/** Busca por texto no título e filtro por estado (FR-024). */
export function SearchBar({
  query,
  phase,
  onQuery,
  onPhase,
}: {
  query: string;
  phase: PhaseFilter;
  onQuery: (q: string) => void;
  onPhase: (p: PhaseFilter) => void;
}) {
  return (
    <div className="row" role="search">
      <div className="field">
        <label htmlFor="vitrine-q">Buscar lotes</label>
        <input id="vitrine-q" value={query} placeholder="Time, temporada…" onChange={(e) => onQuery(e.target.value)} />
      </div>
      <div className="field" style={{ flex: '0 1 200px' }}>
        <label htmlFor="vitrine-phase">Estado</label>
        <select id="vitrine-phase" value={phase} onChange={(e) => onPhase(e.target.value as PhaseFilter)}>
          <option value="all">Todos</option>
          <option value="live">Ao vivo</option>
          <option value="scheduled">Agendados</option>
          <option value="ended">Encerrados</option>
        </select>
      </div>
    </div>
  );
}
