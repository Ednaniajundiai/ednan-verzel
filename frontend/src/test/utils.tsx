import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { vi } from 'vitest';
import { AuthContext, type AuthValue, type User } from '../auth/AuthContext';

export function fakeAuth(user: User | null, overrides: Partial<AuthValue> = {}): AuthValue {
  return {
    user,
    token: user ? 'token' : null,
    loading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  };
}

export const auctioneer: User = { id: 'a1', username: 'leiloeira', name: 'Leiloeira', role: 'auctioneer' };
export const bidder: User = { id: 'b1', username: 'licitante', name: 'Licitante', role: 'bidder' };

/** Mostra o caminho atual: permite conferir redirecionamentos. */
export function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

export function renderWithAuth(ui: ReactElement, auth: AuthValue, path = '/') {
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={ui} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

/** Resposta JSON para `fetch` simulado. */
export function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}
