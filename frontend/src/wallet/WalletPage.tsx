import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import { formatBRL } from '../lib/money';
import { useLiveRefresh } from '../lib/useLiveRefresh';
import { DepositForm } from './DepositForm';

interface Wallet {
  balance_cents: number;
  committed_cents: number;
  available_cents: number;
  committed_lots: { lot_id: string; title: string; amount_cents: number }[];
}

/** Carteira do licitante (spec 004, H2): três saldos, comprometido por lote e depósito. */
export function WalletPage() {
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Wallet>('/wallet')
      .then((w) => {
        setWallet(w);
        setError(null);
      })
      .catch(() => setError('Não foi possível carregar a carteira. Tente de novo.'));
  }, []);

  useEffect(load, [load]);
  useLiveRefresh(load, wallet?.committed_lots.map((l) => l.lot_id) ?? []);

  return (
    <section className="stack">
      <div className="page-head">
        <h1>Carteira</h1>
      </div>
      {error && <p className="notice error">{error}</p>}
      {wallet && (
        <>
          <div className="stats">
            <div className="card stat">
              <span className="muted">Saldo total</span>
              <strong data-testid="balance">{formatBRL(wallet.balance_cents)}</strong>
            </div>
            <div className="card stat">
              <span className="muted">Comprometido</span>
              <strong data-testid="committed">{formatBRL(wallet.committed_cents)}</strong>
              <span className="muted">em lotes que você lidera</span>
            </div>
            <div className="card stat">
              <span className="muted">Disponível</span>
              <strong data-testid="available">{formatBRL(wallet.available_cents)}</strong>
              <span className="muted">total − comprometido</span>
            </div>
          </div>

          <div className="card stack">
            <h2>Depositar</h2>
            <p className="muted">Depósito simulado, de R$ 1,00 a R$ 100.000,00.</p>
            <DepositForm onDeposited={load} />
          </div>

          <div className="card stack">
            <h2>Lotes que compõem o comprometido</h2>
            {wallet.committed_lots.length === 0 ? (
              <p className="muted">Você não lidera nenhum lote agora.</p>
            ) : (
              <ul className="plain-list">
                {wallet.committed_lots.map((l) => (
                  <li key={l.lot_id}>
                    <Link to={`/lotes/${l.lot_id}`}>{l.title}</Link> <strong>{formatBRL(l.amount_cents)}</strong>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  );
}
