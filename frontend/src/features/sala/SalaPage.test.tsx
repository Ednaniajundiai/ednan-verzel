import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext } from '../../auth/AuthContext';
import { resetClock } from '../../lib/clock';
import { setSocketForTesting } from '../../lib/socket';
import { installFakeSocket } from '../../test/fakeSocket';
import { auctioneer, bidder, fakeAuth, jsonResponse } from '../../test/utils';
import type { LotDetail } from '../lots/types';
import { SalaPage } from './SalaPage';

const NOW = Date.parse('2026-10-28T20:00:00.000Z');
const iso = (offsetMs: number) => new Date(NOW + offsetMs).toISOString();
const ME = 'meu-pseudonimo00';

function detail(over: Partial<LotDetail> = {}): LotDetail {
  return {
    id: 'L1',
    item: {
      id: 'i1',
      title: 'Camisa Flamengo 2019',
      description: '',
      image_url: '/images/fla.png',
      size: 'M',
      condition: 'nova',
      attributes: { team: 'Flamengo', season: '2019-2020' },
    },
    status: 'open',
    phase: 'live',
    result: null,
    starting_price_cents: 10_000,
    min_increment_cents: 1_000,
    current_price_cents: 12_000,
    next_minimum_cents: 13_000,
    leader: ME,
    you_are_leading: true,
    bid_count: 2,
    starts_at: iso(-3_600_000),
    ends_at: iso(600_000),
    original_ends_at: iso(600_000),
    extended: false,
    settled_at: null,
    audit_head_hash: 'h',
    standings: [
      { bidder: ME, max_cents: 12_000 },
      { bidder: 'outro00000000000', max_cents: 11_000 },
    ],
    viewer: { bidder: ME, has_bid: true, position: 1, total_bidders: 2, leading: true },
    bids: [
      { id: 2, bidder: ME, amount_cents: 12_000, at: iso(-60_000) },
      { id: 1, bidder: 'outro00000000000', amount_cents: 11_000, at: iso(-120_000) },
    ],
    ...over,
  };
}

let sock: ReturnType<typeof installFakeSocket>;
let lotResponses: LotDetail[];
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers({ now: NOW, shouldAdvanceTime: true });
  sock = installFakeSocket();
  lotResponses = [detail()];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/lots/L1' && (!init?.method || init.method === 'GET')) {
      const lot = lotResponses.length > 1 ? lotResponses.shift()! : lotResponses[0]!;
      return jsonResponse({ server_now: new Date(Date.now()).toISOString(), lot });
    }
    return jsonResponse({ error: { code: 'NOT_FOUND', message: 'x' } }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  setSocketForTesting(null);
  resetClock();
});

function renderSala(auth = fakeAuth(bidder)) {
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={['/lotes/L1']}>
        <Routes>
          <Route path="/lotes/:id" element={<SalaPage />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

const lotLoads = () =>
  fetchMock.mock.calls.filter(([url, init]) => url === '/api/lots/L1' && (init?.method ?? 'GET') === 'GET').length;
const norm = (t: string | null | undefined) => (t ?? '').replace(/\s/g, ' ');

describe('SalaPage ao vivo (FR-010 a FR-017)', () => {
  it('mostra item, lance atual, mínimo, contagem e histórico com "você"; entra na sala do socket', async () => {
    renderSala();
    expect(await screen.findByRole('heading', { name: 'Camisa Flamengo 2019' })).toBeTruthy();
    expect((screen.getByRole('img') as HTMLImageElement).src).toContain('/images/fla.png');
    expect(norm(screen.getByTestId('current-price').textContent)).toContain('R$ 120,00');
    expect(norm(screen.getByTestId('next-minimum').textContent)).toContain('R$ 130,00');
    expect(screen.getByTestId('countdown').textContent).toBe('10:00');
    const rows = screen.getAllByTestId('bid-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]!.textContent).toMatch(/você/);
    expect(rows[1]!.textContent).not.toMatch(/você/);
    expect(sock.emitted).toContainEqual(['lot:join', 'L1']);
  });

  it('"Você está ganhando" vira "Você foi superado" quando outro pseudônimo dá lance', async () => {
    renderSala();
    expect(await screen.findByText('Você está ganhando')).toBeTruthy();
    sock.fire('bid:placed', {
      lot_id: 'L1',
      bid_id: 3,
      bidder: 'outro00000000000',
      amount_cents: 13_000,
      bid_count: 3,
      at: iso(1_000),
      ends_at: iso(600_000),
    });
    expect(screen.getByText('Você foi superado')).toBeTruthy();
    expect(norm(screen.getByTestId('current-price').textContent)).toContain('R$ 130,00');
    expect(norm(screen.getByTestId('next-minimum').textContent)).toContain('R$ 140,00');
    expect(screen.getByText('Você está em 2º de 2 licitantes')).toBeTruthy();
    expect(screen.getAllByTestId('bid-row')).toHaveLength(3);
  });

  it('posição "2º de 5" e "Você ainda não deu lance"', async () => {
    lotResponses = [
      detail({
        viewer: { bidder: ME, has_bid: true, position: 2, total_bidders: 5, leading: false },
        standings: [
          { bidder: 'a', max_cents: 50 },
          { bidder: ME, max_cents: 40 },
          { bidder: 'c', max_cents: 30 },
          { bidder: 'd', max_cents: 20 },
          { bidder: 'e', max_cents: 10 },
        ],
      }),
    ];
    const { unmount } = renderSala();
    expect(await screen.findByText('Você está em 2º de 5 licitantes')).toBeTruthy();
    expect(screen.getByText('Você foi superado')).toBeTruthy();
    unmount();

    lotResponses = [detail({ viewer: { bidder: ME, has_bid: false, position: null, total_bidders: 2, leading: false }, bids: [] })];
    renderSala();
    expect(await screen.findByText('Você ainda não deu lance')).toBeTruthy();
    expect(screen.queryByText('Você está ganhando')).toBeNull();
    expect(screen.queryByText('Você foi superado')).toBeNull();
  });

  it('lance recusado mostra a mensagem junto ao campo e mantém o valor', async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        expect(new Headers(init.headers).get('idempotency-key')).toBeTruthy();
        return jsonResponse({ error: { code: 'INSUFFICIENT_FUNDS', message: 'Saldo insuficiente', available_cents: 5_000 } }, 422);
      }
      return jsonResponse({ server_now: new Date(Date.now()).toISOString(), lot: detail({ viewer: { bidder: ME, has_bid: false, position: null, total_bidders: 2, leading: false } }) });
    });
    renderSala();
    const input = (await screen.findByLabelText('Seu lance (R$)')) as HTMLInputElement;
    // Com o relógio falso, o efeito de montagem do BidForm (que sugere o mínimo) fica num
    // setImmediate falso e pode rodar depois da digitação, sobrescrevendo o valor: no Windows a
    // mistura virava "Informe um valor válido em reais.". Esvazia os efeitos pendentes e digita
    // o valor num único `change`, sem depender do tempo entre teclas do `clear`/`type`.
    await act(() => vi.advanceTimersByTimeAsync(0));
    fireEvent.change(input, { target: { value: '150,00' } });
    expect(input.value).toBe('150,00');
    await userEvent.click(screen.getByRole('button', { name: 'Dar lance' }));
    expect(norm((await screen.findByRole('alert')).textContent)).toBe('Saldo insuficiente. Seu saldo disponível é R$ 50,00.');
    expect(input.value).toBe('150,00');
    expect(input.getAttribute('aria-describedby')).toBeTruthy();
  });

  it('lot:extended faz a contagem saltar e avisa "Lote prorrogado"', async () => {
    renderSala();
    await screen.findByTestId('countdown');
    sock.fire('lot:extended', { lot_id: 'L1', ends_at: iso(720_000), previous_ends_at: iso(600_000) });
    expect(screen.getByTestId('countdown').textContent).toBe('12:00');
    expect(screen.getByText(/Lote prorrogado/)).toBeTruthy();
  });

  it('lot:settled desativa o lance e mostra o resultado com "Você venceu"', async () => {
    renderSala();
    await screen.findByLabelText('Seu lance (R$)');
    sock.fire('lot:settled', { lot_id: 'L1', status: 'settled', winner: ME, final_price_cents: 12_000, at: iso(0) });
    expect(screen.queryByLabelText('Seu lance (R$)')).toBeNull();
    expect(norm(screen.getByText(/Arrematado por/).textContent)).toContain('R$ 120,00');
    expect(screen.getByText('Você venceu')).toBeTruthy();
  });

  it('"Você não venceu" para quem deu lance e perdeu', async () => {
    lotResponses = [detail({ leader: 'outro00000000000', viewer: { bidder: ME, has_bid: true, position: 2, total_bidders: 2, leading: false } })];
    renderSala();
    await screen.findByText('Você foi superado');
    sock.fire('lot:settled', { lot_id: 'L1', status: 'settled', winner: 'outro00000000000', final_price_cents: 13_000, at: iso(0) });
    expect(screen.getByText('Você não venceu')).toBeTruthy();
  });

  it('visitante não vê posição nem indicador e é convidado a entrar', async () => {
    lotResponses = [detail({ viewer: undefined, you_are_leading: false })];
    renderSala(fakeAuth(null));
    await screen.findByRole('heading', { name: 'Camisa Flamengo 2019' });
    expect(screen.queryByText(/Você está/)).toBeNull();
    expect(screen.queryByLabelText('Seu lance (R$)')).toBeNull();
    expect(screen.getByRole('link', { name: /Entre para dar lance/ }).getAttribute('href')).toBe('/entrar');
  });

  it('leiloeiro vê a sala sem a área de lance', async () => {
    lotResponses = [detail({ viewer: { bidder: 'x', has_bid: false, position: null, total_bidders: 2, leading: false } })];
    renderSala(fakeAuth(auctioneer));
    await screen.findByRole('heading', { name: 'Camisa Flamengo 2019' });
    expect(screen.queryByLabelText('Seu lance (R$)')).toBeNull();
    expect(screen.getByText(/Leiloeiros não dão lances/)).toBeTruthy();
  });

  it('queda do socket mostra "Reconectando…" e, ao voltar, recarrega o lote', async () => {
    renderSala();
    await screen.findByText('Você está ganhando');
    const before = lotLoads();
    sock.drop();
    expect(screen.getByText('Reconectando…')).toBeTruthy();
    sock.restore();
    await waitFor(() => expect(lotLoads()).toBe(before + 1));
    expect(screen.queryByText('Reconectando…')).toBeNull();
    expect(sock.emitted.filter(([n]) => n === 'lot:join').length).toBeGreaterThanOrEqual(2);
  });
});

describe('SalaPage agendado e cancelado (FR-023)', () => {
  it('agendado: contagem até o início, lance inicial, incremento e lance desativado; vira ao vivo no horário', async () => {
    const scheduled = detail({
      phase: 'scheduled',
      starts_at: iso(5_000),
      current_price_cents: null,
      next_minimum_cents: 10_000,
      bids: [],
      standings: [],
      viewer: { bidder: ME, has_bid: false, position: null, total_bidders: 0, leading: false },
    });
    lotResponses = [scheduled, { ...scheduled, phase: 'live' }];
    renderSala();
    expect(await screen.findByText(/Começa em/)).toBeTruthy();
    expect(screen.getByTestId('countdown').textContent).toBe('00:05');
    expect(norm(screen.getByText(/Lance inicial/).textContent)).toContain('R$ 100,00');
    expect(norm(screen.getByText(/Incremento mínimo/).textContent)).toContain('R$ 10,00');
    expect((screen.getByRole('button', { name: 'Dar lance' }) as HTMLButtonElement).disabled).toBe(true);

    await act(async () => {
      vi.advanceTimersByTime(6_000);
    });
    await waitFor(() => expect(screen.queryByText(/Começa em/)).toBeNull());
    expect((screen.getByRole('button', { name: 'Dar lance' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('cancelado por link direto: "Lote cancelado", sem área de lance', async () => {
    lotResponses = [detail({ phase: 'cancelled', status: 'cancelled', current_price_cents: null, bids: [], standings: [] })];
    renderSala();
    expect(await screen.findByText('Lote cancelado')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Dar lance' })).toBeNull();
  });

  it('lot:cancelled com a sala aberta troca para "Lote cancelado"', async () => {
    lotResponses = [detail({ current_price_cents: null, bids: [], standings: [], viewer: { bidder: ME, has_bid: false, position: null, total_bidders: 0, leading: false } })];
    renderSala();
    await screen.findByRole('button', { name: 'Dar lance' });
    sock.fire('lot:cancelled', { lot_id: 'L1' });
    expect(screen.getByText('Lote cancelado')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Dar lance' })).toBeNull();
  });
});
