import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AuthContext } from '../auth/AuthContext';
import { RequireRole } from '../auth/RequireRole';
import { auctioneer, bidder, fakeAuth, LocationProbe } from '../test/utils';

function renderPanel(auth: ReturnType<typeof fakeAuth>) {
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={['/painel']}>
        <Routes>
          <Route
            path="/painel"
            element={
              <RequireRole role="auctioneer">
                <p>conteúdo do painel</p>
              </RequireRole>
            }
          />
          <Route path="*" element={<p>outra página</p>} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe('RequireRole (FR-002, FR-005)', () => {
  it('leiloeiro vê o conteúdo do painel', () => {
    renderPanel(fakeAuth(auctioneer));
    expect(screen.getByText('conteúdo do painel')).toBeTruthy();
  });

  it('licitante é redirecionado para a página inicial', () => {
    renderPanel(fakeAuth(bidder));
    expect(screen.queryByText('conteúdo do painel')).toBeNull();
    expect(screen.getByTestId('location').textContent).toBe('/');
  });

  it('visitante é levado ao login', () => {
    renderPanel(fakeAuth(null));
    expect(screen.queryByText('conteúdo do painel')).toBeNull();
    expect(screen.getByTestId('location').textContent).toBe('/entrar');
  });

  it('enquanto a sessão carrega, não decide nada', () => {
    renderPanel(fakeAuth(null, { loading: true, token: 't' }));
    expect(screen.queryByText('conteúdo do painel')).toBeNull();
    expect(screen.getByTestId('location').textContent).toBe('/painel');
  });
});
