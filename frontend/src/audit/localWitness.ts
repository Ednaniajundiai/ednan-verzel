/**
 * Testemunha do navegador (spec 004, S-06): guarda o último `{seq, head_hash}`
 * visto por lote. Numa visita seguinte, avisa se a trilha não contém mais esse
 * elo — mesmo que o servidor inteiro tenha sido adulterado.
 */
const key = (lotId: string) => `leilao.witness.${lotId}`;

interface Seen {
  seq: number;
  head_hash: string;
}

function read(lotId: string): Seen | null {
  try {
    const raw = localStorage.getItem(key(lotId));
    const v = raw ? (JSON.parse(raw) as Seen) : null;
    return v && typeof v.seq === 'number' && typeof v.head_hash === 'string' ? v : null;
  } catch {
    return null;
  }
}

export function rememberHead(lotId: string, seq: number, headHash: string): void {
  const current = read(lotId);
  if (current && current.seq >= seq) return;
  try {
    localStorage.setItem(key(lotId), JSON.stringify({ seq, head_hash: headHash }));
  } catch {
    // sem storage: segue sem testemunha local
  }
}

export function checkLocalWitness(lotId: string, entries: { seq: number; hash: string }[]): { seen: Seen | null; missing: boolean } {
  const seen = read(lotId);
  if (!seen) return { seen: null, missing: false };
  return { seen, missing: entries[seen.seq - 1]?.hash !== seen.head_hash };
}
