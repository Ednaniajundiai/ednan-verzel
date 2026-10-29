import { useEffect, useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api/client';

export interface Team {
  id: string;
  name: string;
  league: string | null;
  country: string | null;
  badge_url: string | null;
}

export interface Jersey {
  id: string;
  team_id: string | null;
  team_name: string | null;
  league: string | null;
  season: string | null;
  kind: string | null;
  kind_label: string | null;
  title: string;
  image_url: string | null;
  image_status: 'saved' | 'image_pending' | 'no_image';
}

interface Notice {
  code: 'UPSTREAM_UNAVAILABLE' | 'UPSTREAM_RATE_LIMITED';
  retry_after_seconds?: number;
}

interface TeamSearchResponse {
  source: 'live' | 'cache';
  notice?: Notice;
  teams: Team[];
  selected_team_id: string | null;
  jerseys: Jersey[] | null;
}

interface JerseyListResponse {
  source: 'live' | 'cache';
  notice?: Notice;
  team: Team;
  jerseys: Jersey[];
}

type Tab = 'search' | 'saved';

/** Aviso legível para a fonte fora do ar ou limitada (FR-008). Nunca mostra erro técnico. */
function noticeText(notice: Notice, hasResults: boolean): string {
  if (notice.code === 'UPSTREAM_RATE_LIMITED') {
    const wait = notice.retry_after_seconds ? `Tente de novo em ${notice.retry_after_seconds} s.` : 'Tente de novo em instantes.';
    return `A fonte de camisas limitou as consultas. ${wait}${hasResults ? ' Mostrando o que já está salvo.' : ''}`;
  }
  return hasResults
    ? 'A fonte de camisas está indisponível no momento. Mostrando o que já está salvo; os resultados podem estar desatualizados.'
    : 'A fonte de camisas está indisponível no momento. Você ainda pode criar lotes com as camisas já salvas.';
}

function friendlyError(err: unknown): string {
  if (err instanceof ApiError && err.code === 'VALIDATION') return 'Digite o nome de um time.';
  if (err instanceof ApiError && err.code === 'NOT_FOUND') return 'Time não encontrado. Busque de novo pelo nome.';
  return 'Não foi possível buscar agora. Tente de novo.';
}

export function CatalogSearch({ onSelect, selectedId }: { onSelect: (jersey: Jersey) => void; selectedId?: string }) {
  const [tab, setTab] = useState<Tab>('search');
  const [term, setTerm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [teams, setTeams] = useState<Team[] | null>(null);
  const [team, setTeam] = useState<Team | null>(null);
  const [jerseys, setJerseys] = useState<Jersey[] | null>(null);
  const [saved, setSaved] = useState<Jersey[] | null>(null);

  useEffect(() => {
    if (tab !== 'saved' || saved) return;
    api<{ jerseys: Jersey[] }>('/auctioneer/catalog/jerseys')
      .then((res) => setSaved(res.jerseys))
      .catch(() => setError('Não foi possível carregar as camisas salvas. Tente de novo.'));
  }, [tab, saved]);

  async function onSearch(e: FormEvent) {
    e.preventDefault();
    if (!term.trim()) {
      setError('Digite o nome de um time.');
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    setTeam(null);
    setJerseys(null);
    try {
      const res = await api<TeamSearchResponse>(`/auctioneer/catalog/teams?q=${encodeURIComponent(term.trim())}`);
      setTeams(res.teams);
      setNotice(res.notice ?? null);
      if (res.jerseys) {
        setTeam(res.teams.find((t) => t.id === res.selected_team_id) ?? null);
        setJerseys(res.jerseys);
      }
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function openTeam(next: Team) {
    setBusy(true);
    setError(null);
    try {
      const res = await api<JerseyListResponse>(`/auctioneer/catalog/teams/${encodeURIComponent(next.id)}/jerseys`);
      setTeam(res.team);
      setJerseys(res.jerseys);
      setNotice(res.notice ?? null);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  const searched = teams !== null;
  const hasResults = (jerseys?.length ?? 0) > 0 || (!jerseys && (teams?.length ?? 0) > 0);
  const nothingFound = searched && !notice && (jerseys ? jerseys.length === 0 : teams!.length === 0);

  return (
    <section className="stack" aria-label="Catálogo de camisas">
      <div className="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === 'search'} onClick={() => setTab('search')}>
          Buscar por time
        </button>
        <button type="button" role="tab" aria-selected={tab === 'saved'} onClick={() => setTab('saved')}>
          Camisas salvas
        </button>
      </div>

      {tab === 'search' && (
        <>
          <form className="row" onSubmit={onSearch} role="search">
            <div className="field">
              <label htmlFor="catalog-term">Time</label>
              <input
                id="catalog-term"
                value={term}
                maxLength={60}
                placeholder="Ex.: Flamengo, Palmeiras, Barcelona"
                onChange={(e) => setTerm(e.target.value)}
              />
            </div>
            <button className="primary" type="submit" disabled={busy}>
              Buscar
            </button>
          </form>

          {busy && <p className="muted">Buscando…</p>}
          {error && (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="notice warning" role="status">
              {noticeText(notice, hasResults)}
            </p>
          )}
          {nothingFound && <p className="muted">Nenhuma camisa encontrada para este time.</p>}

          {teams && teams.length > 0 && !jerseys && (
            <div className="stack">
              <p className="muted">Escolha o time:</p>
              <div className="row">
                {teams.map((t) => (
                  <button key={t.id} type="button" onClick={() => openTeam(t)} disabled={busy}>
                    {t.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {jerseys && jerseys.length > 0 && (
            <>
              {team && (
                <p className="muted">
                  Camisas de <strong>{team.name}</strong>
                  {team.league ? ` · ${team.league}` : ''}
                  {teams && teams.length > 1 && (
                    <>
                      {' '}
                      ·{' '}
                      <button type="button" className="link" onClick={() => setJerseys(null)}>
                        ver outros times
                      </button>
                    </>
                  )}
                </p>
              )}
              <JerseyGrid jerseys={jerseys} onSelect={onSelect} selectedId={selectedId} />
            </>
          )}
        </>
      )}

      {tab === 'saved' && (
        <>
          {error && (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          {saved === null && !error && <p className="muted">Carregando…</p>}
          {saved?.length === 0 && <p className="muted">Nenhuma camisa salva ainda. Busque um time para começar.</p>}
          {saved && saved.length > 0 && <JerseyGrid jerseys={saved} onSelect={onSelect} selectedId={selectedId} />}
        </>
      )}
    </section>
  );
}

function JerseyGrid({
  jerseys,
  onSelect,
  selectedId,
}: {
  jerseys: Jersey[];
  onSelect: (jersey: Jersey) => void;
  selectedId?: string;
}) {
  return (
    <div className="grid">
      {jerseys.map((j) => {
        const disabled = j.image_status === 'no_image';
        return (
          <button
            key={j.id}
            type="button"
            className={`card jersey${selectedId === j.id ? ' selected' : ''}`}
            disabled={disabled}
            aria-pressed={selectedId === j.id}
            onClick={() => onSelect(j)}
          >
            {j.image_url ? (
              <img src={j.image_url} alt="" loading="lazy" />
            ) : (
              <span className="placeholder-img">{disabled ? 'Sem imagem: não pode virar lote' : 'Imagem pendente'}</span>
            )}
            <strong>{j.title}</strong>
            <span className="muted">
              {[j.team_name, j.season, j.kind_label].filter(Boolean).join(' · ')}
            </span>
          </button>
        );
      })}
    </div>
  );
}
