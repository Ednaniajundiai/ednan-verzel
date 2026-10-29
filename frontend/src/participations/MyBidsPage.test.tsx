import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setSocketForTesting } from '../lib/socket';
import { installFakeSocket } from '../test/fakeSocket';
import { jsonResponse } from '../test/utils';
import { MyBidsPage } from './MyBidsPage';

const NOW = Date.parse('2026-10-28T20:00:00.000Z');
let sock: ReturnType<typeof installFakeSocket>;
let data: Record<string, unknown>;

const live = (leading: boolean) => ({
  lot_id: 'L1',
  title: 'Camisa Flamengo 2019',
  image_url: null,
  phase: 'live',
  current_price_cents: 20_000,
  my_max_cents: leading ? 20_000 : 15_000,
  leading,
  ends_at: new Date(NOW + 300_000).toISOString(),
});

beforeEach(() => {
  vi.useFakeTimers({ now: NOW, shouldAdvanceTime: true });
  sock = installFakeSocket();
  data = {
    server_now: new Date(NOW).toISOString(),
    participating: [live(true)],
    closed: [
      { lot_id: 'L2', title: 'Camisa Palmeiras 2021', image_url: null, outcome: 'won', final_price_cents: 25_000, my_max_cents: 25_000, settled_at: new Date(NOW).toISOString(), receipt_url: '/comprovante/L2.tokentokentokentoken12' },
      { lot_id: 'L3', title: 'Camisa Santos 2011', image_url: null, outcome: 'lost', final_price_cents: 30_000, my_max_cents: 10_000, settled_at: new Date(NOW).toISOString() },
    ],
  };
  vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ ...data, server_now: new Date(Date.now()).toISOString() })));
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  setSocketForTesting(null);
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <MyBidsPage />
    </MemoryRouter>,
  );
const norm = (t: string | null | undefined) => (t ?? '').replace(/\s/g, ' ');

describe('MyBidsPage (FR-014 a FR-016)', () => {
  it('participando: lance atual, meu maior lance, situação, tempo restante e atalho para a sala', async () => {
    renderPage();
    const section = await screen.findByRole('region', { name: 'Participando' });
    const text = norm(section.textContent);
    expect(text).toContain('R$ 200,00');
    expect(text).toContain('Seu maior lance: R$ 200,00');
    expect(within(section).getByText('Ganhando')).toBeTruthy();
    expect(within(section).getByTestId('countdown').textContent).toBe('05:00');
    expect(within(section).getByRole('link', { name: 'Ir para a sala' }).getAttribute('href')).toBe('/lotes/L1');
  });

  it('encerrados: arrematado com comprovante e botão de copiar; não arrematado sem comprovante', async () => {
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    renderPage();
    const section = await screen.findByRole('region', { name: 'Encerrados' });
    expect(norm(within(section).getByText(/Arrematado por/).textContent)).toContain('R$ 250,00');
    expect(within(section).getByRole('link', { name: 'Ver comprovante' }).getAttribute('href')).toBe('/comprovante/L2.tokentokentokentoken12');
    expect(within(section).getByText('Não arrematado')).toBeTruthy();
    expect(within(section).getAllByRole('link', { name: 'Ver comprovante' })).toHaveLength(1);

    await userEvent.click(within(section).getByRole('button', { name: 'Copiar link' }));
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/comprovante/L2.tokentokentokentoken12`);
    expect(await screen.findByText('Link copiado')).toBeTruthy();
  });

  it('lista vazia mostra o atalho para a vitrine', async () => {
    data = { participating: [], closed: [] };
    renderPage();
    expect(await screen.findByText(/Você ainda não deu lances/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Ver a vitrine' }).getAttribute('href')).toBe('/');
  });

  it('a situação muda para "Superado" ao receber bid:outbid', async () => {
    renderPage();
    await screen.findByText('Ganhando');
    data = { ...data, participating: [live(false)] };
    sock.fire('bid:outbid', { lot_id: 'L1', amount_cents: 20_000 });
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    await waitFor(() => expect(screen.getByText('Superado')).toBeTruthy());
  });
});
