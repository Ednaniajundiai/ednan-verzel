import { normalizeText } from '../../lib/text';
import { clubOf } from './clubs';
import type { Phase } from './phase';

export { normalizeText };

export type PhaseFilter = 'all' | Exclude<Phase, 'cancelled'>;

interface Filterable {
  phase: Phase;
  item: { title: string; attributes?: Record<string, string> };
}

/** Texto no título, estado e clube (código da spec 006; `null` = todos), somados. */
export function filterLots<T extends Filterable>(lots: T[], query: string, phase: PhaseFilter, club: string | null = null): T[] {
  const q = normalizeText(query);
  return lots.filter(
    (l) =>
      (phase === 'all' || l.phase === phase) &&
      (!q || normalizeText(l.item.title).includes(q)) &&
      (!club || clubOf(l.item.attributes?.team)?.code === club),
  );
}
