import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { api, ApiError } from '../../api/client';
import { formatBRL } from '../../lib/money';

export interface PanelLot {
  id: string;
  title: string;
  image_url: string | null;
  size: string | null;
  condition: string | null;
  phase: 'scheduled' | 'live' | 'ended' | 'cancelled';
  outcome: 'open' | 'sold' | 'unsold' | 'cancelled';
  starting_price_cents: number;
  current_price_cents: number | null;
  final_price_cents: number | null;
  bid_count: number;
  can_cancel: boolean;
  starts_at: string;
  ends_at: string;
}

interface PanelResponse {
  server_now: string;
  total_received_cents: number;
  lots: PanelLot[];
}

const dateTime = (iso: string) =>
  new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });

/** Situação e resultado em texto (FR-017). */
export function resultLabel(lot: PanelLot): string {
  switch (lot.outcome) {
    case 'sold':
      return `Arrematado por ${formatBRL(lot.final_price_cents ?? 0)}`;
    case 'unsold':
      return 'Não arrematado';
    case 'cancelled':
      return 'Cancelado';
    default:
      if (lot.phase === 'scheduled') return `Agendado · começa ${dateTime(lot.starts_at)}`;
      if (lot.current_price_cents === null) return 'Ao vivo · sem lances ainda';
      return `Ao vivo · ${formatBRL(lot.current_price_cents)} (${lot.bid_count} ${lot.bid_count === 1 ? 'lance' : 'lances'})`;
  }
}

const badgeClass: Record<PanelLot['outcome'], string> = {
  sold: 'badge success',
  unsold: 'badge',
  cancelled: 'badge danger',
  open: 'badge primary',
};

export function PanelPage() {
  const location = useLocation();
  const created = (location.state as { created?: string } | null)?.created;
  const [data, setData] = useState<PanelResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    api<PanelResponse>('/auctioneer/lots')
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch(() => setError('Não foi possível carregar seus lotes. Tente de novo.'));
  }, []);

  useEffect(load, [load]);

  async function cancel(lot: PanelLot) {
    if (!window.confirm(`Cancelar o lote "${lot.title}"? Ele deixa de aceitar lances.`)) return;
    setBusyId(lot.id);
    setRowError(null);
    try {
      await api(`/auctioneer/lots/${lot.id}/cancel`, { method: 'POST' });
      load();
    } catch (err) {
      setRowError({ id: lot.id, message: err instanceof ApiError ? err.message : 'Não foi possível cancelar. Tente de novo.' });
      load();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="stack">
      <div className="page-head">
        <h1>Painel do leiloeiro</h1>
        <Link to="/painel/novo" className="badge primary" style={{ padding: '8px 14px', fontSize: '1rem' }}>
          + Novo lote
        </Link>
      </div>

      {created && (
        <p className="notice success" role="status">
          Lote publicado.
        </p>
      )}
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}

      {data && (
        <>
          <div className="card stat">
            <span className="muted">Total recebido</span>
            <strong data-testid="total-received">{formatBRL(data.total_received_cents)}</strong>
            <span className="muted">Soma dos lotes arrematados. Cancelados e não arrematados não entram.</span>
          </div>

          {data.lots.length === 0 ? (
            <p className="muted">
              Você ainda não tem lotes. <Link to="/painel/novo">Crie o primeiro</Link>.
            </p>
          ) : (
            <div className="card table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Lote</th>
                    <th scope="col">Situação</th>
                    <th scope="col">Período</th>
                    <th scope="col">
                      <span className="visually-hidden">Ações</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.lots.map((lot) => (
                    <tr key={lot.id}>
                      <td>
                        <div className="row" style={{ alignItems: 'center', flexWrap: 'nowrap' }}>
                          {lot.image_url && <img className="thumb" style={{ width: 48 }} src={lot.image_url} alt="" />}
                          <div>
                            <strong>{lot.title}</strong>
                            <div className="muted">
                              {[lot.size, lot.condition?.replaceAll('_', ' ')].filter(Boolean).join(' · ')} · inicial{' '}
                              {formatBRL(lot.starting_price_cents)}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className={badgeClass[lot.outcome]}>{resultLabel(lot)}</span>
                      </td>
                      <td className="muted">
                        {dateTime(lot.starts_at)} → {dateTime(lot.ends_at)}
                      </td>
                      <td>
                        {lot.can_cancel && (
                          <button type="button" className="danger" disabled={busyId === lot.id} onClick={() => cancel(lot)}>
                            Cancelar
                          </button>
                        )}
                        {rowError?.id === lot.id && (
                          <p className="field-error" role="alert">
                            {rowError.message}
                          </p>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
