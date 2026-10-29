import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { resetClock, syncClock } from '../../lib/clock';
import { Countdown } from './Countdown';

afterEach(() => {
  vi.useRealTimers();
  resetClock();
});

const REAL = Date.parse('2026-10-28T20:00:00.000Z');
const DEVICE_AHEAD = REAL + 5 * 60_000;

function seconds(text: string) {
  const parts = text.split(':').map(Number);
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

describe('Countdown (FR-014, FR-009)', () => {
  it('com o aparelho adiantado 5 min, mostra o tempo do relógio da casa (erro ≤ 1 s)', () => {
    vi.useFakeTimers({ now: DEVICE_AHEAD });
    syncClock(new Date(REAL).toISOString(), DEVICE_AHEAD, DEVICE_AHEAD);
    render(<Countdown target={new Date(REAL + 90_000).toISOString()} />);
    expect(Math.abs(seconds(screen.getByTestId('countdown').textContent!) - 90)).toBeLessThanOrEqual(1);
    act(() => vi.advanceTimersByTime(30_000));
    expect(Math.abs(seconds(screen.getByTestId('countdown').textContent!) - 60)).toBeLessThanOrEqual(1);
  });

  it('salta quando o fim muda e avisa ao zerar', () => {
    vi.useFakeTimers({ now: REAL });
    const onZero = vi.fn();
    const { rerender } = render(<Countdown target={new Date(REAL + 10_000).toISOString()} onZero={onZero} />);
    rerender(<Countdown target={new Date(REAL + 130_000).toISOString()} onZero={onZero} />);
    expect(screen.getByTestId('countdown').textContent).toBe('02:10');
    act(() => vi.advanceTimersByTime(131_000));
    expect(screen.getByTestId('countdown').textContent).toBe('00:00');
    expect(onZero).toHaveBeenCalled();
  });

  it('acima de uma hora mostra horas', () => {
    vi.useFakeTimers({ now: REAL });
    render(<Countdown target={new Date(REAL + 3 * 3_600_000 + 61_000).toISOString()} />);
    expect(screen.getByTestId('countdown').textContent).toBe('03:01:01');
  });
});
