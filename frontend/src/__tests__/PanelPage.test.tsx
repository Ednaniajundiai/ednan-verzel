import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PanelPage, type PanelLot } from '../pages/auctioneer/PanelPage';
import { jsonResponse } from '../test/utils';

afterEach(() => vi.unstubAllGlobals());

const lot = (over: Partial<PanelLot>): PanelLot => ({
  id: 'l1',
  title: 'Camisa Flamengo 2019',
  image_url: null,
  size: 'M',
  condition: 'nova',
  phase: 'live',
  outcome: 'open',
  starting_price_cents: 10_000,
  current_price_cents: null,
  final_price_cents: null,
  bid_count: 0,
  can_cancel: true,
  starts_at: '2026-10-28T10:00:00.000Z',
  ends_at: '2026-10-28T12:00:00.000Z',
  ...over,
});

const panel = {
  server_now: '2026-10-28T11:00:00.000Z',
  total_received_cents: 15_500,
  lots: [
    lot({ id: 'sold', title: 'Vendida', phase: 'ended', outcome: 'sold', final_price_cents: 12_000, can_cancel: false }),
    lot({ id: 'unsold', title: 'Sem lances', phase: 'ended', outcome: 'unsold', can_cancel: false }),
    lot({ id: 'cancelled', title: 'Cancelada', phase: 'cancelled', outcome: 'cancelled', can_cancel: false }),
    lot({ id: 'open', title: 'Aberta' }),
  ],
};

describe('PanelPage (FR-015, FR-017, FR-018)', () => {
  it('mostra resultado de cada lote, total recebido e cancelar só onde cabe', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(panel)));
    render(
      <MemoryRouter>
        <PanelPage />
      </MemoryRouter>,
    );
    expect((await screen.findByTestId('total-received')).textContent?.replace(/\s/g, ' ')).toBe('R$ 155,00');
    expect(screen.getByText(/Arrematado por R\$\s120,00/)).toBeTruthy();
    expect(screen.getByText('Não arrematado')).toBeTruthy();
    expect(screen.getByText('Cancelado')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Cancelar' })).toHaveLength(1);
  });

  it('cancelar recusado mostra o motivo do servidor', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        url.endsWith('/cancel')
          ? jsonResponse({ error: { code: 'LOT_HAS_BIDS', message: 'O lote já recebeu lances' } }, 409)
          : jsonResponse(panel),
      ),
    );
    render(
      <MemoryRouter>
        <PanelPage />
      </MemoryRouter>,
    );
    await userEvent.click(await screen.findByRole('button', { name: 'Cancelar' }));
    expect(await screen.findByText('O lote já recebeu lances')).toBeTruthy();
  });
});
