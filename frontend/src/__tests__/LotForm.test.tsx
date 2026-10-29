import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Jersey } from '../pages/auctioneer/CatalogSearch';
import { LotForm } from '../pages/auctioneer/LotForm';
import { jsonResponse } from '../test/utils';

afterEach(() => vi.unstubAllGlobals());

const jersey: Jersey = {
  id: '6d1f3c8e-0b7a-4a51-9f3e-2f1c9d7b5a10',
  team_id: '134296',
  team_name: 'Flamengo',
  league: 'Brazilian Serie A',
  season: '2019-2020',
  kind: '1st',
  kind_label: 'Titular',
  title: 'Camisa Flamengo 2019-2020 titular',
  image_url: '/images/a.png',
  image_status: 'saved',
};

/** Valor para <input type="datetime-local"> a `minutes` de agora. */
function localInput(minutes: number) {
  const d = new Date(Date.now() + minutes * 60_000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function renderForm(onCreated = vi.fn()) {
  render(
    <MemoryRouter>
      <LotForm jersey={jersey} onCreated={onCreated} />
    </MemoryRouter>,
  );
  return onCreated;
}

async function fillValid() {
  await userEvent.selectOptions(screen.getByLabelText('Tamanho'), 'M');
  await userEvent.selectOptions(screen.getByLabelText('Estado de conservação'), 'nova');
  await userEvent.type(screen.getByLabelText('Fim'), localInput(120));
  await userEvent.type(screen.getByLabelText('Lance inicial (R$)'), '150,00');
  await userEvent.type(screen.getByLabelText('Incremento mínimo (R$)'), '10');
}

const submit = () => userEvent.click(screen.getByRole('button', { name: 'Publicar lote' }));
const errorOf = (label: string) => {
  const input = screen.getByLabelText(label);
  const id = input.getAttribute('aria-describedby');
  return id ? document.getElementById(id)?.textContent ?? null : null;
};

describe('LotForm (FR-011, FR-012)', () => {
  it('sugere o título a partir de time, temporada e tipo', () => {
    renderForm();
    expect((screen.getByLabelText('Título') as HTMLInputElement).value).toBe('Camisa Flamengo 2019-2020 titular');
  });

  it('cada campo inválido mostra a mensagem ao lado e o envio fica bloqueado', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    renderForm();
    await userEvent.clear(screen.getByLabelText('Título'));
    await userEvent.type(screen.getByLabelText('Início'), localInput(-10));
    await userEvent.type(screen.getByLabelText('Fim'), localInput(-20));
    await userEvent.type(screen.getByLabelText('Lance inicial (R$)'), '0');
    await userEvent.type(screen.getByLabelText('Incremento mínimo (R$)'), 'abc');
    await submit();

    expect(errorOf('Título')).toMatch(/informe o título/i);
    expect(errorOf('Tamanho')).toMatch(/escolha um tamanho/i);
    expect(errorOf('Estado de conservação')).toMatch(/escolha o estado/i);
    expect(errorOf('Início')).toMatch(/passado/i);
    expect(errorOf('Fim')).toMatch(/depois do início/i);
    expect(errorOf('Lance inicial (R$)')).toMatch(/maior que zero/i);
    expect(errorOf('Incremento mínimo (R$)')).toMatch(/valor válido/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('envia centavos inteiros e avisa a criação', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => jsonResponse({ id: 'lot-1' }, 201));
    vi.stubGlobal('fetch', fetchMock);
    const onCreated = renderForm();
    await fillValid();
    await submit();

    expect(onCreated).toHaveBeenCalledWith('lot-1');
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe('/api/auctioneer/lots');
    const body = JSON.parse(String(init?.body));
    expect(body).toMatchObject({
      item_id: jersey.id,
      title: 'Camisa Flamengo 2019-2020 titular',
      size: 'M',
      condition: 'nova',
      starting_price_cents: 15_000,
      min_increment_cents: 1_000,
    });
    expect(body.starts_at).toBeUndefined();
    expect(Number.isInteger(body.starting_price_cents)).toBe(true);
  });

  it('erro de campo devolvido pelo servidor aparece no campo', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(
          { error: { code: 'VALIDATION', message: 'Entrada inválida', issues: { starts_at: ['O início não pode estar no passado'] } } },
          400,
        ),
      ),
    );
    renderForm();
    await fillValid();
    await submit();
    expect(await screen.findByText('O início não pode estar no passado')).toBeTruthy();
    expect(errorOf('Início')).toBe('O início não pode estar no passado');
  });

  it('imagem indisponível: mostra a mensagem do servidor', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(
          { error: { code: 'IMAGE_UNAVAILABLE', message: 'A imagem desta camisa está indisponível agora. Tente de novo em instantes.' } },
          503,
        ),
      ),
    );
    renderForm();
    await fillValid();
    await submit();
    expect(await screen.findByText(/imagem desta camisa está indisponível/i)).toBeTruthy();
  });
});
