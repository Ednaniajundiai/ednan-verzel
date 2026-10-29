import { formatBRL } from '../../lib/money';
import type { LotDetail } from '../lots/types';

/** Resultado do lote encerrado (FR-015). */
export function ResultPanel({ lot }: { lot: LotDetail }) {
  const sold = lot.result === 'sold' || lot.status === 'settled';
  const viewer = lot.viewer;
  return (
    <div className="card result-panel stack">
      <strong>{sold ? `Arrematado por ${formatBRL(lot.current_price_cents ?? 0)}` : 'Encerrado sem vencedor'}</strong>
      {viewer?.has_bid && (
        <p className={sold && lot.leader === viewer.bidder ? 'badge success' : 'badge'}>
          {sold && lot.leader === viewer.bidder ? 'Você venceu' : 'Você não venceu'}
        </p>
      )}
      {lot.status === 'open' && <p className="muted">Apurando o resultado…</p>}
    </div>
  );
}
