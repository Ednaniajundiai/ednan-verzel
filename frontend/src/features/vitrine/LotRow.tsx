import type { PublicLot } from '../lots/types';
import { LotCard } from './LotCard';

/** Fileira temática que rola para o lado (ideia 1, Catawiki); vazia, não aparece. */
export function LotRow({ id, title, lots }: { id: string; title: string; lots: PublicLot[] }) {
  if (lots.length === 0) return null;
  return (
    <section className="lot-row-section" aria-labelledby={`row-${id}`}>
      <h2 id={`row-${id}`}>{title}</h2>
      <div className="lot-row">
        {lots.map((l) => (
          <LotCard key={l.id} lot={l} />
        ))}
      </div>
    </section>
  );
}
