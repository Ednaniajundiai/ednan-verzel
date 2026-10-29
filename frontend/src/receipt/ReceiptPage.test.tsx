import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { jsonResponse, LocationProbe } from '../test/utils';
import { ReceiptPage } from './ReceiptPage';

afterEach(() => vi.unstubAllGlobals());

const receipt = (over: Record<string, unknown> = {}) => ({
  receipt_id: 'L2.tok',
  code: 'K7PQ2MZX',
  lot: { id: 'L2', number: '3AA9AF76', title: 'Camisa Palmeiras 2021', image_url: '/images/pal.png', attributes: { team: 'Palmeiras', season: '2021' }, size: 'M', condition: 'nova' },
  winner: '21530ab8ef86abf8',
  final_price_cents: 25_000,
  settled_at: '2026-10-28T20:15:47.000Z',
  verdict: { verdict: 'intact', failure_kind: null, broken_at_seq: null },
  tampered: false,
  audit_url: '/auditoria/L2',
  ...over,
});

function renderReceipt(body: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(body, status)));
  return render(
    <MemoryRouter initialEntries={['/comprovante/L2.tok']}>
      <Routes>
        <Route path="/comprovante/:id" element={<ReceiptPage />} />
        <Route path="/auditoria/:id" element={<p>página de auditoria</p>} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  );
}
const norm = (t: string | null | undefined) => (t ?? '').replace(/\s/g, ' ');

describe('ReceiptPage (FR-018, FR-019, SC-005)', () => {
  it('mostra item, número, valor, momento, código, pseudônimo e veredito', async () => {
    renderReceipt(receipt());
    expect(await screen.findByRole('heading', { name: /Camisa Palmeiras 2021/ })).toBeTruthy();
    const text = norm(document.body.textContent);
    expect(text).toContain('3AA9AF76');
    expect(text).toContain('R$ 250,00');
    expect(text).toContain('K7PQ2MZX');
    expect(text).toContain('21530ab8ef86abf8');
    expect(text).toMatch(/Palmeiras · 2021/);
    expect(screen.getByRole('img').getAttribute('src')).toBe('/images/pal.png');
    expect(screen.getByTestId('receipt-verdict').textContent).toMatch(/íntegro/i);
    expect(document.querySelector('time')?.getAttribute('dateTime')).toBe('2026-10-28T20:15:47.000Z');
  });

  it('histórico adulterado: aviso no comprovante', async () => {
    renderReceipt(receipt({ tampered: true, verdict: { verdict: 'tampered', failure_kind: 'altered', broken_at_seq: 2 } }));
    expect((await screen.findByTestId('receipt-verdict')).textContent).toMatch(/adulterado/i);
  });

  it('chega à auditoria com 1 clique', async () => {
    renderReceipt(receipt());
    await userEvent.click(await screen.findByRole('link', { name: /Auditar este lote/ }));
    expect(screen.getByTestId('location').textContent).toBe('/auditoria/L2');
  });

  it('404 → "Comprovante não encontrado"', async () => {
    renderReceipt({ error: { code: 'NOT_FOUND', message: 'Comprovante não encontrado' } }, 404);
    expect(await screen.findByText('Comprovante não encontrado.')).toBeTruthy();
  });
});
