import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { resetClock } from '../../lib/clock';
import { setSocketForTesting } from '../../lib/socket';
import { installFakeSocket } from '../../test/fakeSocket';
import { jsonResponse } from '../../test/utils';
import type { PublicLot } from '../lots/types';
import { VitrinePage } from './VitrinePage';

const NOW = Date.parse('2026-10-28T20:00:00.000Z');
const iso = (offsetMs: number) => new Date(NOW + offsetMs).toISOString();

function lot(id: string, title: string, over: Partial<PublicLot> = {}): PublicLot {
  return {
    id,
    item: { id: `i-${id}`, title, description: '', image_url: null, size: 'M', condition: 'nova', attributes: {} },
    status: 'open',
    phase: 'live',
    result: null,
    starting_price_cents: 10_000,
    min_increment_cents: 1_000,
    current_price_cents: null,
    next_minimum_cents: 10_000,
    leader: null,
    you_are_leading: false,
    bid_count: 0,
    starts_at: iso(-3_600_000),
    ends_at: iso(600_000),
    original_ends_at: iso(600_000),
    extended: false,
    settled_at: null,
    audit_head_hash: 'h',
    ...over,
  };
}

let sock: ReturnType<typeof installFakeSocket>;
let responses: PublicLot[][];

beforeEach(() => {
  vi.useFakeTimers({ now: NOW, shouldAdvanceTime: true });
  sock = installFakeSocket();
  responses = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      const lots = responses.length > 1 ? responses.shift()! : responses[0]!;
      return jsonResponse({ server_now: new Date(Date.now()).toISOString(), lots });
    }),
  );
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  setSocketForTesting(null);
  resetClock();
});

const renderVitrine = () =>
  render(
    <MemoryRouter>
      <VitrinePage />
    </MemoryRouter>,
  );
const section = (name: string) => screen.getByRole('region', { name });
const norm = (t: string | null | undefined) => (t ?? '').replace(/\s/g, ' ');

const fla = lot('1', 'Camisa Flamengo 2019', { current_price_cents: 12_000, bid_count: 2 });
const pal = lot('2', 'Camisa Palmeiras 2021', { phase: 'scheduled', starts_at: iso(3_000), ends_at: iso(3_600_000) });
const sp = lot('3', 'Camisa São Paulo 2005', { phase: 'ended', status: 'settled', result: 'sold', current_price_cents: 30_000 });
const vas = lot('4', 'Camisa Vasco 1998', { phase: 'ended', status: 'unsold', result: 'unsold' });

describe('VitrinePage (FR-020 a FR-022)', () => {
  it('três seções, sem cancelados, cartão com a informação da fase', async () => {
    responses = [[fla, pal, sp, vas, lot('5', 'Camisa Cancelada', { phase: 'cancelled', status: 'cancelled' })]];
    renderVitrine();
    await screen.findByText('Camisa Flamengo 2019');
    expect(screen.queryByText('Camisa Cancelada')).toBeNull();

    const live = section('Ao vivo');
    expect(within(live).getByText('Camisa Flamengo 2019')).toBeTruthy();
    expect(norm(within(live).getByText(/Lance atual/).textContent)).toContain('R$ 120,00');
    expect(within(live).getByTestId('countdown').textContent).toBe('10:00');

    const scheduled = section('Agendados');
    expect(norm(within(scheduled).getByText(/Lance inicial/).textContent)).toContain('R$ 100,00');
    expect(within(scheduled).getByText(/Começa em/)).toBeTruthy();

    const ended = section('Encerrados');
    expect(norm(within(ended).getByText(/Arrematado por/).textContent)).toContain('R$ 300,00');
    expect(within(ended).getByText('Sem vencedor')).toBeTruthy();
    expect(within(live).getByRole('link', { name: /Camisa Flamengo 2019/ }).getAttribute('href')).toBe('/lotes/1');
  });

  it('agendado passa para Ao vivo ao zerar a contagem e depois da nova carga, sem recarregar a página', async () => {
    responses = [[fla, pal], [fla, { ...pal, phase: 'live' }]];
    renderVitrine();
    await screen.findByText('Camisa Palmeiras 2021');
    expect(within(section('Agendados')).getByText('Camisa Palmeiras 2021')).toBeTruthy();
    await act(async () => {
      vi.advanceTimersByTime(4_000);
    });
    await waitFor(() => expect(within(section('Ao vivo')).getByText('Camisa Palmeiras 2021')).toBeTruthy());
    expect(within(section('Agendados')).getByText('Nenhum lote agendado')).toBeTruthy();
  });

  it('lot:cancelled tira o cartão; eventos atualizam lance e fim; seção vazia tem mensagem', async () => {
    responses = [[fla, pal]];
    renderVitrine();
    await screen.findByText('Camisa Flamengo 2019');
    expect(within(section('Encerrados')).getByText('Nenhum lote encerrado')).toBeTruthy();

    sock.fire('bid:placed', { lot_id: '1', bid_id: 9, bidder: 'x', amount_cents: 13_000, bid_count: 3, at: iso(0), ends_at: iso(720_000) });
    expect(norm(within(section('Ao vivo')).getByText(/Lance atual/).textContent)).toContain('R$ 130,00');
    expect(within(section('Ao vivo')).getByTestId('countdown').textContent).toBe('12:00');

    sock.fire('lot:cancelled', { lot_id: '1' });
    expect(screen.queryByText('Camisa Flamengo 2019')).toBeNull();
    expect(within(section('Ao vivo')).getByText('Nenhum lote ao vivo agora')).toBeTruthy();
  });

  it('lot:settled move o lote para Encerrados com o resultado', async () => {
    responses = [[fla]];
    renderVitrine();
    await screen.findByText('Camisa Flamengo 2019');
    sock.fire('lot:settled', { lot_id: '1', status: 'settled', winner: 'x', final_price_cents: 12_000, at: iso(0) });
    expect(within(section('Encerrados')).getByText('Camisa Flamengo 2019')).toBeTruthy();
  });
});

describe('busca e filtro (FR-024)', () => {
  it('busca sem resultado mostra "Nenhum lote encontrado" e um botão para limpar', async () => {
    responses = [[fla, pal, sp]];
    renderVitrine();
    await screen.findByText('Camisa Flamengo 2019');
    await userEvent.type(screen.getByLabelText('Buscar lotes'), 'corinthians');
    expect(screen.getByText('Nenhum lote encontrado')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Limpar busca' }));
    expect(screen.getByText('Camisa Flamengo 2019')).toBeTruthy();
  });

  it('busca sem acento e filtro por fase; um lote que muda de fase continua respeitando os dois', async () => {
    responses = [[fla, pal, sp], [fla, { ...pal, phase: 'live' }, sp]];
    renderVitrine();
    await screen.findByText('Camisa Flamengo 2019');
    await userEvent.type(screen.getByLabelText('Buscar lotes'), 'sao paulo');
    expect(screen.getByText('Camisa São Paulo 2005')).toBeTruthy();
    expect(screen.queryByText('Camisa Flamengo 2019')).toBeNull();

    await userEvent.clear(screen.getByLabelText('Buscar lotes'));
    await userEvent.type(screen.getByLabelText('Buscar lotes'), 'camisa');
    await userEvent.selectOptions(screen.getByLabelText('Estado'), 'scheduled');
    expect(screen.queryByRole('region', { name: 'Ao vivo' })).toBeNull();
    expect(within(section('Agendados')).getByText('Camisa Palmeiras 2021')).toBeTruthy();

    await act(async () => {
      vi.advanceTimersByTime(4_000);
    });
    await waitFor(() => expect(screen.queryByText('Camisa Palmeiras 2021')).toBeNull());
    // Continua respeitando o filtro: a seção Ao vivo não aparece.
    expect(screen.queryByRole('region', { name: 'Ao vivo' })).toBeNull();
  });
});
