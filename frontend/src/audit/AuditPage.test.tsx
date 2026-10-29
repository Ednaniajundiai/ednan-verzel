import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { jsonResponse } from '../test/utils';
import { AuditPage } from './AuditPage';
import type { AuditEntry, AuditResponse } from './types';

afterEach(() => vi.unstubAllGlobals());

const entry = (seq: number, event_type: string, payload: Record<string, unknown>): AuditEntry => ({
  lot_id: 'L1',
  seq,
  event_type,
  payload_canonical: JSON.stringify(payload),
  prev_hash: 'p',
  hash: `h${seq}`,
  signature: 's',
});

function response(over: Partial<AuditResponse> = {}): AuditResponse {
  return {
    lot_id: 'L1',
    algorithm: 'sha256+ed25519',
    entries: [
      entry(1, 'lot_opened', { title: 'Camisa Flamengo 2019', starting_price_cents: 10_000, starts_at: '2026-10-28T20:00:00.000Z', ends_at: '2026-10-28T21:00:00.000Z' }),
      entry(2, 'bid_placed', { bid_id: 1, bidder: 'a1b2c3d4e5f60718', amount_cents: 12_000, at: '2026-10-28T20:05:00.000Z' }),
      entry(3, 'lot_extended', { bid_id: 1, ends_at_before: '2026-10-28T21:00:00.000000Z', ends_at_after: '2026-10-28T21:02:00.000000Z', at: '2026-10-28T20:58:00.000Z' }),
      entry(4, 'lot_settled', { winner: 'a1b2c3d4e5f60718', final_price_cents: 12_000, bid_count: 1, at: '2026-10-28T21:02:00.000Z' }),
      entry(5, 'evento_novo', { motivo: 'teste' }),
    ],
    lot: {
      id: 'L1',
      title: 'Camisa Flamengo 2019',
      image_url: '/images/fla.png',
      attributes: { team: 'Flamengo' },
      size: 'M',
      condition: 'nova',
      status: 'settled',
      phase: 'ended',
      starts_at: '2026-10-28T20:00:00.000Z',
      ends_at: '2026-10-28T21:02:00.000Z',
      starting_price_cents: 10_000,
      current_price_cents: 12_000,
      bid_count: 1,
      audit_head_hash: 'h4',
    },
    witness: null,
    verdict: {
      valid: true,
      verdict: 'intact',
      failure_kind: null,
      broken_at_seq: null,
      failure_reason: null,
      witness_ok: null,
      head_matches_lot: true,
      ends_at_mismatch: false,
    },
    ...over,
  };
}

function renderAudit(body: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(body, status)));
  return render(
    <MemoryRouter initialEntries={['/auditoria/L1']}>
      <Routes>
        <Route path="/auditoria/:id" element={<AuditPage />} />
      </Routes>
    </MemoryRouter>,
  );
}
const norm = (t: string | null | undefined) => (t ?? '').replace(/\s/g, ' ');

describe('AuditPage (FR-001 a FR-004)', () => {
  it('lista os eventos em ordem com tipo, pseudônimo, valor e data; imagem local; veredito íntegro', async () => {
    renderAudit(response());
    expect(await screen.findByRole('heading', { name: /Camisa Flamengo 2019/ })).toBeTruthy();
    expect((screen.getByRole('img') as HTMLImageElement).src).toContain('/images/fla.png');
    const items = screen.getAllByTestId('audit-event');
    expect(items.map((i) => i.getAttribute('data-type'))).toEqual(['lot_opened', 'bid_placed', 'lot_extended', 'lot_settled', 'evento_novo']);
    expect(within(items[0]!).getByText('Abertura do lote')).toBeTruthy();
    expect(within(items[1]!).getByText('Lance')).toBeTruthy();
    expect(within(items[1]!).getByText('a1b2c3d4e5f60718')).toBeTruthy();
    expect(norm(items[1]!.textContent)).toContain('R$ 120,00');
    expect(items[1]!.querySelector('time')).toBeTruthy();
    expect(within(items[2]!).getByText('Prorrogação anti-sniping')).toBeTruthy();
    expect(within(items[3]!).getByText('Arrematado')).toBeTruthy();
    // tipo desconhecido em forma genérica
    expect(within(items[4]!).getByText('evento_novo')).toBeTruthy();
    expect(norm(items[4]!.textContent)).toContain('motivo: teste');
    expect(screen.getByTestId('verdict').textContent).toMatch(/Íntegro/);
  });

  it('adulterado: mostra o evento da quebra e a provável causa', async () => {
    renderAudit(
      response({
        verdict: {
          ...response().verdict,
          valid: false,
          verdict: 'tampered',
          failure_kind: 'missing',
          broken_at_seq: 3,
          failure_reason: 'falta o evento 2 antes deste',
        },
      }),
    );
    const banner = await screen.findByTestId('verdict');
    expect(banner.textContent).toMatch(/Adulterado/);
    expect(banner.textContent).toMatch(/evento 3/);
    expect(banner.textContent).toMatch(/evento ausente/);
    expect(screen.getAllByTestId('audit-event')[2]!.className).toMatch(/broken/);
  });

  it('lote sem lances avisa "ainda não há lances"', async () => {
    renderAudit(response({ entries: [response().entries[0]!] }));
    expect(await screen.findByText(/ainda não há lances/i)).toBeTruthy();
  });

  it('lote inexistente: "Lote não encontrado", sem erro técnico', async () => {
    renderAudit({ error: { code: 'NOT_FOUND', message: 'Lote não encontrado' } }, 404);
    expect(await screen.findByText('Lote não encontrado.')).toBeTruthy();
  });
});
