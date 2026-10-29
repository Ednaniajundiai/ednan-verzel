/**
 * Relógio da casa no navegador (D-10 da 003). O banco decide abertura e fim;
 * aqui só se corrige a exibição: offset = server_now − (envio + resposta)/2.
 */
let offsetMs = 0;

export function syncClock(serverNowIso: string, sentAtMs: number, receivedAtMs: number): void {
  const server = Date.parse(serverNowIso);
  if (Number.isNaN(server)) return;
  offsetMs = Math.round(server - (sentAtMs + receivedAtMs) / 2);
}

export function clockOffsetMs(): number {
  return offsetMs;
}

/** Agora, no relógio da casa (ms desde a época). */
export function serverNow(): number {
  return Date.now() + offsetMs;
}

export function resetClock(): void {
  offsetMs = 0;
}

/** Faz a chamada e, se a resposta trouxer `server_now`, corrige o relógio. */
export async function withClock<T extends { server_now?: string }>(call: () => Promise<T>): Promise<T> {
  const sent = Date.now();
  const res = await call();
  if (res.server_now) syncClock(res.server_now, sent, Date.now());
  return res;
}
