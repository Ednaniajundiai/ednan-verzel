import { formatBRL } from '../../lib/money';
import type { BidEntry } from '../lots/types';

const time = (iso: string) => new Date(iso).toLocaleTimeString('pt-BR');

/** Histórico do mais recente para o mais antigo; os lances do usuário aparecem como "você". */
export function BidHistory({ bids, me }: { bids: BidEntry[]; me?: string }) {
  if (!bids.length) return <p className="muted">Nenhum lance ainda.</p>;
  return (
    <ol className="bid-history">
      {bids.map((b) => (
        <li key={b.id} data-testid="bid-row" className={b.bidder === me ? 'mine' : undefined}>
          <span className="bidder">
            {b.bidder === me ? <strong>você</strong> : <code title="pseudônimo neste lote">{b.bidder}</code>}
          </span>
          <span className="amount">{formatBRL(b.amount_cents)}</span>
          <time className="muted" dateTime={b.at}>
            {time(b.at)}
          </time>
        </li>
      ))}
    </ol>
  );
}
