import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CatalogSearch, type Jersey } from '../pages/auctioneer/CatalogSearch';
import { jsonResponse } from '../test/utils';

afterEach(() => vi.unstubAllGlobals());

const jersey = (over: Partial<Jersey> = {}): Jersey => ({
  id: 'j1',
  team_id: '134296',
  team_name: 'Flamengo',
  league: 'Brazilian Serie A',
  season: '2019-2020',
  kind: '1st',
  kind_label: 'Titular',
  title: 'Camisa Flamengo 2019-2020 titular',
  image_url: '/images/a.png',
  image_status: 'saved',
  ...over,
});
const flamengo = { id: '134296', name: 'Flamengo', league: 'Brazilian Serie A', country: 'Brazil', badge_url: null };
const flamengoU20 = { ...flamengo, id: '140112', name: 'Flamengo RJ U20' };

function stubApi(routes: Record<string, () => Response | Promise<Response>>) {
  const fetchMock = vi.fn(async (url: string) => {
    const key = Object.keys(routes).find((k) => url.startsWith(k));
    return key ? routes[key]!() : jsonResponse({ error: { code: 'NOT_FOUND', message: 'x' } }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function search(term: string) {
  await userEvent.type(screen.getByLabelText('Time'), term);
  await userEvent.click(screen.getByRole('button', { name: 'Buscar' }));
}

describe('CatalogSearch (FR-006, FR-008)', () => {
  it('fonte indisponível: mostra o aviso e as camisas salvas', async () => {
    stubApi({
      '/api/auctioneer/catalog/teams?q=': () =>
        jsonResponse({
          source: 'cache',
          notice: { code: 'UPSTREAM_UNAVAILABLE' },
          teams: [flamengo],
          selected_team_id: flamengo.id,
          jerseys: [jersey()],
        }),
    });
    render(<CatalogSearch onSelect={() => {}} />);
    await search('Flamengo');
    expect(await screen.findByText(/fonte de camisas está indisponível/i)).toBeTruthy();
    expect(screen.getByText(/podem estar desatualizados/i)).toBeTruthy();
    expect(screen.getByText('Camisa Flamengo 2019-2020 titular')).toBeTruthy();
  });

  it('fonte indisponível e nada salvo: diz que ainda dá para usar as camisas salvas', async () => {
    stubApi({
      '/api/auctioneer/catalog/teams?q=': () =>
        jsonResponse({ source: 'cache', notice: { code: 'UPSTREAM_UNAVAILABLE' }, teams: [], selected_team_id: null, jerseys: null }),
    });
    render(<CatalogSearch onSelect={() => {}} />);
    await search('Bangu');
    expect(await screen.findByText(/ainda pode criar lotes com as camisas já salvas/i)).toBeTruthy();
  });

  it('limite de consultas: mostra "tente de novo em N s"', async () => {
    stubApi({
      '/api/auctioneer/catalog/teams?q=': () =>
        jsonResponse({
          source: 'cache',
          notice: { code: 'UPSTREAM_RATE_LIMITED', retry_after_seconds: 96 },
          teams: [],
          selected_team_id: null,
          jerseys: null,
        }),
    });
    render(<CatalogSearch onSelect={() => {}} />);
    await search('Flamengo');
    expect(await screen.findByText(/tente de novo em 96 s/i)).toBeTruthy();
  });

  it('sem resultado: "nenhuma camisa encontrada para este time"', async () => {
    stubApi({
      '/api/auctioneer/catalog/teams?q=': () =>
        jsonResponse({ source: 'live', teams: [flamengoU20], selected_team_id: flamengoU20.id, jerseys: [] }),
    });
    render(<CatalogSearch onSelect={() => {}} />);
    await search('Flamengo RJ U20');
    expect(await screen.findByText(/nenhuma camisa encontrada para este time/i)).toBeTruthy();
  });

  it('resposta que já traz camisas abre a grade direto, sem lista de times', async () => {
    const onSelect = vi.fn();
    stubApi({
      '/api/auctioneer/catalog/teams?q=': () =>
        jsonResponse({
          source: 'live',
          teams: [flamengo, flamengoU20],
          selected_team_id: flamengo.id,
          jerseys: [jersey(), jersey({ id: 'j2', kind: '2nd', kind_label: 'Reserva', title: 'Camisa Flamengo 2019-2020 reserva' })],
        }),
    });
    render(<CatalogSearch onSelect={onSelect} />);
    await search('Flamengo');
    const card = await screen.findByRole('button', { name: /Camisa Flamengo 2019-2020 reserva/ });
    expect(screen.queryByRole('button', { name: 'Flamengo RJ U20' })).toBeNull();
    await userEvent.click(card);
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'j2' }));
  });

  it('vários times: escolher um time carrega as camisas dele', async () => {
    stubApi({
      '/api/auctioneer/catalog/teams?q=': () =>
        jsonResponse({ source: 'live', teams: [flamengo, flamengoU20], selected_team_id: null, jerseys: null }),
      '/api/auctioneer/catalog/teams/134296/jerseys': () =>
        jsonResponse({ source: 'live', team: flamengo, jerseys: [jersey()] }),
    });
    render(<CatalogSearch onSelect={() => {}} />);
    await search('Fla');
    await userEvent.click(await screen.findByRole('button', { name: 'Flamengo' }));
    expect(await screen.findByText('Camisa Flamengo 2019-2020 titular')).toBeTruthy();
  });

  it('camisa sem imagem aparece desabilitada', async () => {
    stubApi({
      '/api/auctioneer/catalog/teams?q=': () =>
        jsonResponse({
          source: 'live',
          teams: [flamengo],
          selected_team_id: flamengo.id,
          jerseys: [jersey({ image_status: 'no_image', image_url: null })],
        }),
    });
    render(<CatalogSearch onSelect={() => {}} />);
    await search('Flamengo');
    const card = await screen.findByRole('button', { name: /Camisa Flamengo/ });
    expect((card as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/sem imagem/i)).toBeTruthy();
  });

  it('nenhum texto técnico de erro chega à tela', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed: ECONNREFUSED 127.0.0.1:3000');
      }),
    );
    render(<CatalogSearch onSelect={() => {}} />);
    await search('Flamengo');
    expect(await screen.findByText(/não foi possível buscar agora/i)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/TypeError|ECONNREFUSED|fetch failed/);
  });

  it('aba "camisas salvas" lista as camisas guardadas localmente', async () => {
    stubApi({ '/api/auctioneer/catalog/jerseys': () => jsonResponse({ jerseys: [jersey({ id: 's1' })] }) });
    render(<CatalogSearch onSelect={() => {}} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Camisas salvas' }));
    expect(await screen.findByText('Camisa Flamengo 2019-2020 titular')).toBeTruthy();
  });
});
