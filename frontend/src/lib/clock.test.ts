import { afterEach, describe, expect, it, vi } from 'vitest';
import { clockOffsetMs, resetClock, serverNow, syncClock } from './clock';

afterEach(() => {
  vi.restoreAllMocks();
  resetClock();
});

describe('relógio da casa (FR-014, D-10)', () => {
  it('offset = server_now − (envio + resposta)/2', () => {
    syncClock('2026-10-28T20:00:00.000Z', Date.parse('2026-10-28T20:00:09.900Z'), Date.parse('2026-10-28T20:00:10.100Z'));
    expect(clockOffsetMs()).toBe(-10_000);
  });

  it('corrige um aparelho adiantado 5 min com erro máximo de 1 s', () => {
    const real = Date.parse('2026-10-28T20:00:00.000Z');
    const device = real + 5 * 60_000;
    vi.spyOn(Date, 'now').mockReturnValue(device + 300);
    // ida e volta de 300 ms; o servidor respondeu no meio do caminho
    syncClock(new Date(real + 150).toISOString(), device, device + 300);
    expect(Math.abs(serverNow() - (real + 300))).toBeLessThanOrEqual(1_000);
  });

  it('sem sincronização, usa o relógio do aparelho', () => {
    vi.spyOn(Date, 'now').mockReturnValue(1_000);
    expect(serverNow()).toBe(1_000);
  });
});
