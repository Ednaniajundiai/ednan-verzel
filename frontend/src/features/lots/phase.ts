export type Phase = 'scheduled' | 'live' | 'ended' | 'cancelled';

/**
 * Fase exibida. Quem decide é o servidor (Const. 3.1): quando o relógio corrigido
 * passa de um marco, a fase fica "a confirmar" (`pending`) até a nova carga.
 */
export function displayPhase(
  lot: { phase: Phase; starts_at: string; ends_at: string },
  nowMs: number,
): { phase: Phase; pending: boolean } {
  if (lot.phase === 'scheduled') return { phase: lot.phase, pending: nowMs >= Date.parse(lot.starts_at) };
  if (lot.phase === 'live') return { phase: lot.phase, pending: nowMs >= Date.parse(lot.ends_at) };
  return { phase: lot.phase, pending: false };
}
