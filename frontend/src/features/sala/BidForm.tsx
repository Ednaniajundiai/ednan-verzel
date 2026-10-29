import { useEffect, useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api/client';
import { formatBRL, parseBRLToCents } from '../../lib/money';
import { bidRefusalMessage } from '../lots/messages';

const toInput = (cents: number) => formatBRL(cents).replace(/^R\$\s/, '');

function newKey(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
}

/**
 * Envio de lance (FR-016): sugere o mínimo, manda uma Idempotency-Key por envio e
 * mostra a recusa junto ao campo, sem perder o valor digitado.
 */
export function BidForm({
  lotId,
  minimumCents,
  disabled,
  onPlaced,
}: {
  lotId: string;
  minimumCents: number;
  disabled: boolean;
  onPlaced: () => void;
}) {
  const [value, setValue] = useState(() => toInput(minimumCents));
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!touched) setValue(toInput(minimumCents));
  }, [minimumCents, touched]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const cents = parseBRLToCents(value);
    if (cents === null || cents <= 0) {
      setError('Informe um valor válido em reais.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api(`/lots/${lotId}/bids`, { body: { amount_cents: cents }, headers: { 'idempotency-key': newKey() } });
      setTouched(false);
      onPlaced();
    } catch (err) {
      setError(err instanceof ApiError ? bidRefusalMessage(err) : 'Não foi possível enviar o lance. Tente de novo.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="bid-form stack" onSubmit={onSubmit} noValidate>
      <div className="field">
        <label htmlFor="bid-amount">Seu lance (R$)</label>
        <div className="row" style={{ flexWrap: 'nowrap' }}>
          <input
            id="bid-amount"
            inputMode="decimal"
            value={value}
            disabled={disabled}
            aria-invalid={!!error}
            aria-describedby={error ? 'bid-error' : 'bid-hint'}
            onChange={(e) => {
              setTouched(true);
              setValue(e.target.value);
            }}
          />
          <button className="primary" type="submit" disabled={disabled || busy}>
            Dar lance
          </button>
        </div>
        {error ? (
          <p className="field-error" id="bid-error" role="alert">
            {error}
          </p>
        ) : (
          <span className="muted" id="bid-hint">
            {`Mínimo: ${formatBRL(minimumCents)}`}
          </span>
        )}
      </div>
    </form>
  );
}
