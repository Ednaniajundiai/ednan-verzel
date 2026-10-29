import { formatBRL } from '../lib/money';
import type { AuditEntry } from './types';

const LABELS: Record<string, string> = {
  lot_opened: 'Abertura do lote',
  bid_placed: 'Lance',
  lot_extended: 'Prorrogação anti-sniping',
  lot_settled: 'Arrematado',
  lot_unsold: 'Encerrado sem vencedor',
  lot_cancelled: 'Cancelado',
};

const dateTime = (iso: unknown) =>
  typeof iso === 'string' && !Number.isNaN(Date.parse(iso))
    ? new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' })
    : null;

function parse(e: AuditEntry): Record<string, unknown> | null {
  try {
    const v: unknown = JSON.parse(e.payload_canonical);
    return v && typeof v === 'object' ? (v as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/**
 * Eventos da trilha, exibidos a partir do conteúdo assinado (`payload_canonical`,
 * S-03 da 004). Tipos conhecidos ganham rótulo; o resto aparece como chave e valor.
 */
export function EventList({ entries, brokenAtSeq }: { entries: AuditEntry[]; brokenAtSeq: number | null }) {
  return (
    <ol className="audit-events">
      {entries.map((e) => {
        const p = parse(e) ?? {};
        const label = LABELS[e.event_type];
        const bidder = (p.bidder ?? p.winner) as string | undefined;
        const cents = (p.amount_cents ?? p.final_price_cents ?? p.starting_price_cents) as number | undefined;
        const when = dateTime(p.at ?? p.starts_at);
        return (
          <li
            key={`${e.seq}-${e.hash}`}
            data-testid="audit-event"
            data-type={e.event_type}
            className={brokenAtSeq === e.seq ? 'broken' : undefined}
          >
            <span className="seq">#{e.seq}</span>
            <div className="stack" style={{ gap: 2 }}>
              <strong>{label ?? <code>{e.event_type}</code>}</strong>
              {label ? (
                <span className="muted">
                  {bidder && (
                    <>
                      {e.event_type === 'lot_settled' ? 'vencedor ' : 'licitante '}
                      <code>{bidder}</code>
                      {' · '}
                    </>
                  )}
                  {typeof cents === 'number' && <>{(e.event_type === 'lot_opened' ? 'lance inicial ' : '') + formatBRL(cents)} · </>}
                  {e.event_type === 'lot_extended' && dateTime(p.ends_at_after) && <>novo fim {dateTime(p.ends_at_after)} · </>}
                  {when && <time dateTime={String(p.at ?? p.starts_at)}>{when}</time>}
                </span>
              ) : (
                <span className="muted">
                  {Object.entries(p)
                    .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
                    .join(' · ')}
                </span>
              )}
            </div>
            <code className="hash" title={`hash ${e.hash}`}>
              {e.hash.slice(0, 12)}…
            </code>
          </li>
        );
      })}
    </ol>
  );
}
