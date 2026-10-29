import { useEffect, useRef, useState } from 'react';
import { serverNow } from '../../lib/clock';

export function formatRemaining(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  if (h >= 48) return `${Math.floor(h / 24)} dias`;
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

/** Contagem regressiva pelo relógio da casa (FR-014). `onZero` dispara uma vez por alvo. */
export function Countdown({ target, onZero }: { target: string; onZero?: () => void }) {
  const targetMs = Date.parse(target);
  const [now, setNow] = useState(() => serverNow());
  const fired = useRef<number | null>(null);

  useEffect(() => {
    setNow(serverNow());
    const timer = setInterval(() => setNow(serverNow()), 250);
    return () => clearInterval(timer);
  }, [targetMs]);

  const remaining = targetMs - now;
  useEffect(() => {
    if (remaining <= 0 && fired.current !== targetMs) {
      fired.current = targetMs;
      onZero?.();
    }
  }, [remaining, targetMs, onZero]);

  return (
    <span className="countdown" data-testid="countdown" aria-live="off">
      {formatRemaining(remaining)}
    </span>
  );
}
