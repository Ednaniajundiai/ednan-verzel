import { useRef, useState, type FormEvent } from 'react';
import { api, ApiError } from '../api/client';
import { formatBRL, parseBRLToCents } from '../lib/money';

const MIN_CENTS = 100;
const MAX_CENTS = 10_000_000;
const LIMIT_MESSAGE = 'O depósito deve ser entre R$ 1,00 e R$ 100.000,00, com até duas casas decimais.';
const SHORTCUTS = [10_000, 50_000, 100_000];

function newKey(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Depósito com valor escolhido (FR-009 a FR-011). A chave de idempotência vale
 * para a tentativa: reenviar (duplo clique, falha de rede) repete a mesma chave;
 * só um depósito confirmado, ou outro valor, gera chave nova.
 */
export function DepositForm({ onDeposited }: { onDeposited: () => void }) {
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const key = useRef(newKey());

  const change = (next: string) => {
    setValue(next);
    setDone(null);
    key.current = newKey();
  };

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setDone(null);
    const cents = parseBRLToCents(value);
    if (cents === null || cents < MIN_CENTS || cents > MAX_CENTS) {
      setError(LIMIT_MESSAGE);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api('/wallet/deposit', { body: { amount_cents: cents }, headers: { 'idempotency-key': key.current } });
      setDone(`Depósito de ${formatBRL(cents)} confirmado.`);
      setValue('');
      key.current = newKey();
      onDeposited();
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === 'VALIDATION'
          ? LIMIT_MESSAGE
          : err instanceof ApiError && err.code !== 'NETWORK' && err.code !== 'INTERNAL'
            ? err.message
            : 'Não foi possível confirmar o depósito. Tente de novo: ele não será feito duas vezes.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={onSubmit} noValidate>
      <div className="field">
        <label htmlFor="deposit-amount">Valor do depósito (R$)</label>
        <input
          id="deposit-amount"
          inputMode="decimal"
          placeholder="250,00"
          value={value}
          aria-invalid={!!error}
          aria-describedby={error ? 'deposit-error' : undefined}
          onChange={(e) => change(e.target.value)}
        />
      </div>
      <div className="row">
        {SHORTCUTS.map((c) => (
          <button key={c} type="button" onClick={() => change(formatBRL(c).replace(/^R\$\s/, ''))}>
            {formatBRL(c).replace(/,00$/, '')}
          </button>
        ))}
        <button className="primary" type="submit" disabled={busy}>
          Depositar
        </button>
      </div>
      {error && (
        <p className="field-error" id="deposit-error" role="alert">
          {error}
        </p>
      )}
      {done && (
        <p className="notice success" role="status">
          {done}
        </p>
      )}
    </form>
  );
}
