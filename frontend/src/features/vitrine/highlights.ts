import { clubOf } from '../lots/clubs';
import type { PublicLot } from '../lots/types';

const ROW_LIMIT = 8;
const time = (iso: string | null) => (iso ? Date.parse(iso) : 0);
const byPhase = (lots: PublicLot[], phase: PublicLot['phase']) => lots.filter((l) => l.phase === phase);

/** Lote do placar da home: o ao vivo que acaba primeiro, senão o próximo agendado, senão o último encerrado. */
export function featuredLot(lots: PublicLot[]): PublicLot | null {
  const live = byPhase(lots, 'live').sort((a, b) => time(a.ends_at) - time(b.ends_at));
  if (live[0]) return live[0];
  const scheduled = byPhase(lots, 'scheduled').sort((a, b) => time(a.starts_at) - time(b.starts_at));
  if (scheduled[0]) return scheduled[0];
  const ended = byPhase(lots, 'ended').sort((a, b) => time(b.settled_at ?? b.ends_at) - time(a.settled_at ?? a.ends_at));
  return ended[0] ?? null;
}

/** Ao vivo pelo fim mais próximo, depois agendados pelo início mais próximo. */
export function endingSoon(lots: PublicLot[]): PublicLot[] {
  const live = byPhase(lots, 'live').sort((a, b) => time(a.ends_at) - time(b.ends_at));
  const scheduled = byPhase(lots, 'scheduled').sort((a, b) => time(a.starts_at) - time(b.starts_at));
  return [...live, ...scheduled].slice(0, ROW_LIMIT);
}

export function mostDisputed(lots: PublicLot[]): PublicLot[] {
  return lots
    .filter((l) => l.bid_count > 0)
    .sort((a, b) => b.bid_count - a.bid_count)
    .slice(0, ROW_LIMIT);
}

export function highestBids(lots: PublicLot[]): PublicLot[] {
  return lots
    .filter((l) => l.current_price_cents !== null)
    .sort((a, b) => b.current_price_cents! - a.current_price_cents!)
    .slice(0, ROW_LIMIT);
}

/** Quantos lotes cada um dos 30 clubes tem, pelo código do clube. */
export function clubCounts(lots: PublicLot[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const l of lots) {
    const club = clubOf(l.item.attributes.team);
    if (club) counts.set(club.code, (counts.get(club.code) ?? 0) + 1);
  }
  return counts;
}
