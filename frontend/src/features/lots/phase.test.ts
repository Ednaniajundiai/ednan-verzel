import { describe, expect, it } from 'vitest';
import { displayPhase } from './phase';

const at = (iso: string) => Date.parse(iso);
const lot = (phase: 'scheduled' | 'live' | 'ended' | 'cancelled') => ({
  phase,
  starts_at: '2026-10-28T20:00:00.000Z',
  ends_at: '2026-10-28T21:00:00.000Z',
});

describe('fase exibida (FR-013, FR-014, Const. 3.1)', () => {
  it('antes dos marcos, mostra a fase do servidor', () => {
    expect(displayPhase(lot('scheduled'), at('2026-10-28T19:59:59Z'))).toEqual({ phase: 'scheduled', pending: false });
    expect(displayPhase(lot('live'), at('2026-10-28T20:30:00Z'))).toEqual({ phase: 'live', pending: false });
  });

  it('ao zerar a contagem, fica "a confirmar" sem trocar de fase antes do servidor', () => {
    expect(displayPhase(lot('scheduled'), at('2026-10-28T20:00:00Z'))).toEqual({ phase: 'scheduled', pending: true });
    expect(displayPhase(lot('live'), at('2026-10-28T21:00:00Z'))).toEqual({ phase: 'live', pending: true });
  });

  it('encerrado e cancelado são finais', () => {
    expect(displayPhase(lot('ended'), at('2030-01-01T00:00:00Z'))).toEqual({ phase: 'ended', pending: false });
    expect(displayPhase(lot('cancelled'), at('2026-10-28T19:00:00Z'))).toEqual({ phase: 'cancelled', pending: false });
  });
});
