import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import { EventList } from './EventList';
import { HowWeVerify } from './HowWeVerify';
import { checkLocalWitness, rememberHead } from './localWitness';
import type { AuditResponse } from './types';
import { VerdictBanner } from './VerdictBanner';

const STATUS_LABEL = { open: 'em andamento', settled: 'arrematado', unsold: 'encerrado sem vencedor', cancelled: 'cancelado' };

/** Página pública de auditoria do lote, sem login (spec 004, H1). */
export function AuditPage() {
  const { id = '' } = useParams();
  const [data, setData] = useState<AuditResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [localMissing, setLocalMissing] = useState<{ seq: number; head_hash: string } | null>(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    api<AuditResponse>(`/audit/lots/${id}`)
      .then((res) => {
        if (!alive) return;
        // Testemunha do navegador (S-06): compara com o que este navegador já viu.
        const local = checkLocalWitness(res.lot_id, res.entries);
        setLocalMissing(local.missing ? local.seen : null);
        const last = res.entries.at(-1);
        if (last && res.verdict.verdict === 'intact') rememberHead(res.lot_id, last.seq, last.hash);
        setData(res);
      })
      .catch((err) => {
        if (!alive) return;
        setError(
          err instanceof ApiError && (err.status === 404 || err.status === 400)
            ? 'Lote não encontrado.'
            : 'Não foi possível carregar a auditoria agora. Tente de novo.',
        );
      });
    return () => {
      alive = false;
    };
  }, [id]);

  if (error) return <p className="notice error">{error}</p>;
  if (!data) return <p className="muted">Carregando…</p>;

  const hasBids = data.entries.some((e) => e.event_type === 'bid_placed');
  return (
    <section className="stack">
      <div className="audit-head">
        {data.lot.image_url && <img className="thumb" src={data.lot.image_url} alt={data.lot.title} />}
        <div className="stack" style={{ gap: 4 }}>
          <span className="muted">Auditoria pública do lote</span>
          <h1>{data.lot.title}</h1>
          <span className="muted">
            Lote <code>{data.lot.id}</code> · {STATUS_LABEL[data.lot.status]}
          </span>
        </div>
      </div>

      <VerdictBanner verdict={data.verdict} />
      {localMissing && (
        <p className="notice warning" role="alert">
          {`Atenção: numa visita anterior, este navegador viu o evento ${localMissing.seq} deste lote, que não está mais no histórico.`}
        </p>
      )}

      <div className="card stack">
        <h2>Histórico ({data.entries.length} eventos)</h2>
        {!hasBids && <p className="muted">Ainda não há lances neste lote.</p>}
        <EventList entries={data.entries} brokenAtSeq={data.verdict.broken_at_seq} />
      </div>

      <HowWeVerify
        lotId={data.lot_id}
        entries={data.entries}
        witness={data.witness}
        lot={data.lot}
        serverVerdict={data.verdict.verdict}
      />
    </section>
  );
}
