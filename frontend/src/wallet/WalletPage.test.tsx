import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext } from '../auth/AuthContext';
import { RequireRole } from '../auth/RequireRole';
import { setSocketForTesting } from '../lib/socket';
import { installFakeSocket } from '../test/fakeSocket';
import { auctioneer, bidder, fakeAuth, jsonResponse, LocationProbe } from '../test/utils';
import { WalletPage } from './WalletPage';

let sock: ReturnType<typeof installFakeSocket>;
let wallet = { balance_cents: 100_000, committed_cents: 30_000, available_cents: 70_000, committed_lots: [{ lot_id: 'L1', title: 'Camisa Flamengo 2019', amount_cents: 30_000 }] };
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  sock = installFakeSocket();
  wallet = { balance_cents: 100_000, committed_cents: 30_000, available_cents: 70_000, committed_lots: [{ lot_id: 'L1', title: 'Camisa Flamengo 2019', amount_cents: 30_000 }] };
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/wallet/deposit') {
      const amount = JSON.parse(String(init!.body)).amount_cents as number;
      wallet = { ...wallet, balance_cents: wallet.balance_cents + amount, available_cents: wallet.available_cents + amount };
      return jsonResponse({ wallet, replayed: false });
    }
    return jsonResponse(wallet);
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  setSocketForTesting(null);
});

function renderWallet(auth = fakeAuth(bidder)) {
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={['/carteira']}>
        <Routes>
          <Route
            path="/carteira"
            element={
              <RequireRole role="bidder">
                <WalletPage />
              </RequireRole>
            }
          />
          <Route path="*" element={<p>outra</p>} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}
const money = (id: string) => (screen.getByTestId(id).textContent ?? '').replace(/\s/g, ' ');
const deposits = () => fetchMock.mock.calls.filter(([url]) => url === '/api/wallet/deposit');

describe('WalletPage (FR-007 a FR-013)', () => {
  it('mostra os três saldos e os lotes do comprometido', async () => {
    renderWallet();
    await screen.findByText('Camisa Flamengo 2019');
    expect(money('balance')).toBe('R$ 1.000,00');
    expect(money('committed')).toBe('R$ 300,00');
    expect(money('available')).toBe('R$ 700,00');
  });

  it('atalho preenche o valor sem depositar; confirmar deposita e avisa', async () => {
    renderWallet();
    await screen.findByTestId('balance');
    await userEvent.click(screen.getByRole('button', { name: 'R$ 500' }));
    expect((screen.getByLabelText('Valor do depósito (R$)') as HTMLInputElement).value).toBe('500,00');
    expect(deposits()).toHaveLength(0);

    await userEvent.clear(screen.getByLabelText('Valor do depósito (R$)'));
    await userEvent.type(screen.getByLabelText('Valor do depósito (R$)'), '250,00');
    await userEvent.click(screen.getByRole('button', { name: 'Depositar' }));
    expect(await screen.findByText(/Depósito de R\$\s250,00 confirmado/)).toBeTruthy();
    expect(JSON.parse(String(deposits()[0]![1]!.body))).toEqual({ amount_cents: 25_000 });
    await waitFor(() => expect(money('balance')).toBe('R$ 1.250,00'));
    expect(money('available')).toBe('R$ 950,00');
  });

  it('valor fora do limite mostra a mensagem e não envia', async () => {
    renderWallet();
    await screen.findByTestId('balance');
    for (const v of ['0,50', '100.000,01', '10,555', 'abc']) {
      await userEvent.clear(screen.getByLabelText('Valor do depósito (R$)'));
      await userEvent.type(screen.getByLabelText('Valor do depósito (R$)'), v);
      await userEvent.click(screen.getByRole('button', { name: 'Depositar' }));
      expect(screen.getByRole('alert').textContent).toMatch(/entre R\$\s1,00 e R\$\s100\.000,00/);
    }
    expect(deposits()).toHaveLength(0);
  });

  it('reenvio depois de falha usa a mesma chave; depósito novo usa outra', async () => {
    fetchMock.mockImplementationOnce(async () => jsonResponse(wallet)); // carga
    fetchMock.mockImplementationOnce(async () => {
      throw new TypeError('rede caiu');
    });
    renderWallet();
    await screen.findByTestId('balance');
    await userEvent.type(screen.getByLabelText('Valor do depósito (R$)'), '100');
    await userEvent.click(screen.getByRole('button', { name: 'Depositar' }));
    await screen.findByRole('alert');
    await userEvent.click(screen.getByRole('button', { name: 'Depositar' }));
    await screen.findByText(/confirmado/);
    await userEvent.click(screen.getByRole('button', { name: 'R$ 100' }));
    await userEvent.click(screen.getByRole('button', { name: 'Depositar' }));
    await waitFor(() => expect(deposits()).toHaveLength(3));
    const keys = deposits().map(([, init]) => new Headers(init!.headers).get('idempotency-key'));
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
    expect(keys[2]).not.toBe(keys[0]);
  });

  it('os saldos mudam depois de um evento (superado em outra aba)', async () => {
    renderWallet();
    await screen.findByTestId('balance');
    wallet = { ...wallet, committed_cents: 0, available_cents: 100_000, committed_lots: [] };
    sock.fire('bid:outbid', { lot_id: 'L1', amount_cents: 31_000 });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 300));
    });
    await waitFor(() => expect(money('committed')).toBe('R$ 0,00'));
    expect(money('available')).toBe('R$ 1.000,00');
  });

  it('sem login vai para /entrar; leiloeiro é barrado', () => {
    const { unmount } = renderWallet(fakeAuth(null));
    expect(screen.getByTestId('location').textContent).toBe('/entrar');
    unmount();
    renderWallet(fakeAuth(auctioneer));
    expect(screen.getByTestId('location').textContent).toBe('/');
  });
});
