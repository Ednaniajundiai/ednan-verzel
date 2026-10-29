import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth, type Role } from './AuthContext';

/**
 * Guarda de rota por papel. A autoridade é o servidor (403 nas rotas
 * `/auctioneer/*`); aqui só se evita mostrar uma tela que não serve ao papel.
 */
export function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <p className="muted">Carregando…</p>;
  if (!user) return <Navigate to="/entrar" replace state={{ from: location.pathname }} />;
  if (user.role !== role) return <Navigate to="/" replace />;
  return <>{children}</>;
}
