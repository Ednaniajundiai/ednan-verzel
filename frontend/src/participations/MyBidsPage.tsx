import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { withClock } from '../lib/clock';
import { formatBRL } from '../lib/money';
import { useLiveRefresh } from '../lib/useLiveRefresh';
import { Countdown } from '../features/sala/Countdown';

interface Participating {
  lot_id: string;
  title: string;
  image_url: string | null;
  phase: 'live' | 'scheduled';
  current_price_cents: number | null;
  my_max_cents: number;
  leading: boolean;
  ends_at: string;
}

interface Closed {
  lot_id: string;
  title: string;
  image_url: string | null;
  outcome: 'won' | 'lost';
  final_price_cents: number | null;
  my_max_cents: number;
  settled_at: string | null;
  receipt_url?: string;
}

interface Response {
  server_now: string;
  participating: Participating[];
  closed: Closed[];
}

/** "Meus arremates" (spec 004, H3), atualizado ao vivo. */
export function MyBidsPage() {
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const load = useCallback(() => {
    withClock(() => api<Response>('/me/participations'))
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch(() => setError('Não foi possível carregar seus lotes. Tente de novo.'));
  }, []);
  useEffect(load, [load]);
  useLiveRefresh(load, data?.participating.map((p) => p.lot_id) ?? []);

  async function copy(url: string, lotId: string) {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${url}`);
      setCopied(lotId);
    } catch {
      setCopied(null);
      window.prompt('Copie o link do comprovante:', `${window.location.origin}${url}`);
    }
  }

  if (error) return <p className="notice error">{error}</p>;
  if (!data) return <p className="muted">Carregando…</p>;

  const empty = data.participating.length === 0 && data.closed.length === 0;
  return (
    <section className="stack">
      <div className="page-head">
        <h1>Meus arremates</h1>
      </div>
      {empty ? (
        <div className="card stack">
          <p>Você ainda não deu lances.</p>
          <p>
            <Link to="/">Ver a vitrine</Link>
          </p>
        </div>
      ) : (
        <>
          <section aria-labelledby="sec-participando" className="stack">
            <h2 id="sec-participando">Participando</h2>
            {data.participating.length === 0 && <p className="muted">Nenhum lote ao vivo com lance seu agora.</p>}
            {data.participating.map((p) => (
              <article key={p.lot_id} className="card row participation">
                <div className="stack" style={{ gap: 4, flex: 1 }}>
                  <strong>{p.title}</strong>
                  <span>{`Lance atual: ${formatBRL(p.current_price_cents ?? 0)}`}</span>
                  <span className="muted">{`Seu maior lance: ${formatBRL(p.my_max_cents)}`}</span>
                  <span className="muted">
                    Termina em <Countdown target={p.ends_at} onZero={load} />
                  </span>
                </div>
                <span className={p.leading ? 'badge success' : 'badge danger'}>{p.leading ? 'Ganhando' : 'Superado'}</span>
                <Link to={`/lotes/${p.lot_id}`}>Ir para a sala</Link>
              </article>
            ))}
          </section>

          <section aria-labelledby="sec-encerrados" className="stack">
            <h2 id="sec-encerrados">Encerrados</h2>
            {data.closed.length === 0 && <p className="muted">Nenhum lote encerrado ainda.</p>}
            {data.closed.map((c) => (
              <article key={c.lot_id} className="card row participation">
                <div className="stack" style={{ gap: 4, flex: 1 }}>
                  <strong>{c.title}</strong>
                  <span className="muted">{`Seu maior lance: ${formatBRL(c.my_max_cents)}`}</span>
                </div>
                {c.outcome === 'won' && c.receipt_url ? (
                  <>
                    <span className="badge success">{`Arrematado por ${formatBRL(c.final_price_cents ?? 0)}`}</span>
                    <Link to={c.receipt_url}>Ver comprovante</Link>
                    <button type="button" onClick={() => copy(c.receipt_url!, c.lot_id)}>
                      Copiar link
                    </button>
                    {copied === c.lot_id && (
                      <span className="muted" role="status">
                        Link copiado
                      </span>
                    )}
                  </>
                ) : (
                  <span className="badge">Não arrematado</span>
                )}
              </article>
            ))}
          </section>
        </>
      )}
    </section>
  );
}
