import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '../auth/AuthContext';
import { LoginPage } from '../pages/LoginPage';
import { jsonResponse, LocationProbe } from '../test/utils';

afterEach(() => vi.unstubAllGlobals());

function renderLogin() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/entrar']}>
        <Routes>
          <Route path="/entrar" element={<LoginPage />} />
          <Route path="*" element={<p>destino</p>} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </AuthProvider>,
  );
}

async function loginAs(role: 'auctioneer' | 'bidder') {
  const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) =>
    jsonResponse({ token: 'tok', user: { id: 'u1', username: 'x', name: 'X', role } }),
  );
  vi.stubGlobal('fetch', fetchMock);
  renderLogin();
  await userEvent.type(screen.getByLabelText('Usuário'), 'x');
  await userEvent.type(screen.getByLabelText('Senha'), 'senha-forte-123');
  await userEvent.click(screen.getByRole('button', { name: 'Entrar' }));
  return fetchMock;
}

describe('LoginPage (spec 002, cenário 1.1)', () => {
  it('leiloeiro vai para /painel depois de entrar', async () => {
    const fetchMock = await loginAs('auctioneer');
    expect(await screen.findByText('destino')).toBeTruthy();
    expect(screen.getByTestId('location').textContent).toBe('/painel');
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/auth/login');
  });

  it('licitante vai para / depois de entrar', async () => {
    await loginAs('bidder');
    expect(await screen.findByText('destino')).toBeTruthy();
    expect(screen.getByTestId('location').textContent).toBe('/');
  });

  it('credenciais inválidas mostram a mensagem do servidor e ficam na página', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ error: { code: 'UNAUTHORIZED', message: 'Credenciais inválidas' } }, 401)),
    );
    renderLogin();
    await userEvent.type(screen.getByLabelText('Usuário'), 'x');
    await userEvent.type(screen.getByLabelText('Senha'), 'errada');
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }));
    expect(await screen.findByText('Credenciais inválidas')).toBeTruthy();
    expect(screen.getByTestId('location').textContent).toBe('/entrar');
  });
});
