import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import { FAILURE_LABEL, type FailureKind } from '../audit/types';
import { formatBRL } from '../lib/money';

interface Receipt {
  receipt_id: string;
  code: string;
  lot: {
    id: string;
    number: string;
    title: string;
    image_url: string | null;
    attributes: Record<string, string>;
    size: string | null;
    condition: string | null;
  };
  winner: string;
  final_price_cents: number;
  settled_at: string;
  verdict: { verdict: 'intact' | 'tampered'; failure_kind: FailureKind | null; broken_at_seq: number | null };
  tampered: boolean;
  audit_url: string;
}

/** Comprovante público de arremate, sem login (spec 004, H4). Só pseudônimo. */
export function ReceiptPage() {
  const { id = '' } = useParams();
  const [data, setData] = useState<Receipt | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api<Receipt>(`/receipts/${encodeURIComponent(id)}`)
      .then((r) => alive && setData(r))
      .catch((err) => {
        if (!alive) return;
        setError(
          err instanceof ApiError && err.status === 404
            ? 'Comprovante não encontrado.'
            : 'Não foi possível carregar o comprovante agora. Tente de novo.',
        );
      });
    return () => {
      alive = false;
    };
  }, [id]);

  if (error) return <p className="notice error">{error}</p>;
  if (!data) return <p className="muted">Carregando…</p>;

  const attrs = [data.lot.attributes.team, data.lot.attributes.season, data.lot.size, data.lot.condition?.replaceAll('_', ' ')]
    .filter(Boolean)
    .join(' · ');
  return (
    <section className="card receipt stack">
      <span className="muted">Comprovante de arremate · código {data.code}</span>
      <div className="row" style={{ alignItems: 'flex-start' }}>
        {data.lot.image_url && <img className="thumb" style={{ maxWidth: 180 }} src={data.lot.image_url} alt={data.lot.title} />}
        <div className="stack" style={{ gap: 6, flex: 1 }}>
          <h1>{data.lot.title}</h1>
          {attrs && <span className="muted">{attrs}</span>}
          <span>
            Lote nº <code>{data.lot.number}</code>
          </span>
        </div>
      </div>
      <dl className="receipt-fields">
        <dt>Valor arrematado</dt>
        <dd>
          <strong>{formatBRL(data.final_price_cents)}</strong>
        </dd>
        <dt>Encerramento</dt>
        <dd>
          <time dateTime={data.settled_at}>
            {new Date(data.settled_at).toLocaleString('pt-BR', { dateStyle: 'long', timeStyle: 'medium' })}
          </time>
        </dd>
        <dt>Vencedor (pseudônimo no lote)</dt>
        <dd>
          <code>{data.winner}</code>
        </dd>
      </dl>
      <div className={`verdict ${data.tampered ? 'tampered' : 'intact'}`} data-testid="receipt-verdict" role="status">
        {data.tampered ? (
          <span>
            <strong>✖ Atenção: o histórico deste lote foi adulterado</strong>
            {data.verdict.failure_kind && ` (${FAILURE_LABEL[data.verdict.failure_kind]})`}. Os dados acima vêm do registro do
            lote e não puderam ser confirmados pela trilha assinada.
          </span>
        ) : (
          <span>
            <strong>✔ Histórico íntegro</strong>: o resultado confere com a trilha assinada pela casa.
          </span>
        )}
      </div>
      <p>
        <Link to={data.audit_url}>Auditar este lote</Link>
        <span className="muted"> — o mesmo pseudônimo aparece no lance vencedor.</span>
      </p>
      <p className="muted">Este comprovante não mostra nome, usuário nem qualquer dado pessoal do vencedor.</p>
    </section>
  );
}
