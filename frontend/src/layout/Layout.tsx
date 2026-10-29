import type { ReactNode } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { ThemeToggle } from '../theme/ThemeToggle';

/** Moldura comum: navegação muda conforme o papel (FR-002). */
export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          Casa de Leilões
        </Link>
        <nav className="nav">
          {user?.role === 'auctioneer' && (
            <>
              <NavLink to="/painel" end>
                Painel
              </NavLink>
              <NavLink to="/painel/novo">Novo lote</NavLink>
            </>
          )}
          {user?.role !== 'auctioneer' && (
            <NavLink to="/" end>
              Lotes
            </NavLink>
          )}
          {user?.role === 'bidder' && (
            <>
              <NavLink to="/arremates">Meus arremates</NavLink>
              <NavLink to="/carteira">Carteira</NavLink>
            </>
          )}
        </nav>
        <div className="session">
          <ThemeToggle />
          {user ? (
            <>
              <span className="muted">
                {user.name} · {user.role === 'auctioneer' ? 'leiloeiro' : 'licitante'}
              </span>
              <button
                type="button"
                className="link"
                onClick={() => {
                  logout();
                  navigate('/');
                }}
              >
                Sair
              </button>
            </>
          ) : (
            <>
              <NavLink to="/entrar">Entrar</NavLink>
              <NavLink to="/cadastro">Criar conta</NavLink>
            </>
          )}
        </div>
      </header>
      <main className="content">{children}</main>
    </div>
  );
}
