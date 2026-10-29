import type { Phase } from './phase';

export type PhaseFilter = 'all' | Exclude<Phase, 'cancelled'>;

/** Minúsculas, sem acentos e com espaços simples (D-11 da 003). */
export function normalizeText(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

export function filterLots<T extends { phase: Phase; item: { title: string } }>(lots: T[], query: string, phase: PhaseFilter): T[] {
  const q = normalizeText(query);
  return lots.filter((l) => (phase === 'all' || l.phase === phase) && (!q || normalizeText(l.item.title).includes(q)));
}
