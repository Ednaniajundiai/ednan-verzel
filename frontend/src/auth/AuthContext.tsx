import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, ApiError, setAuthToken } from '../api/client';
import { setSocketToken } from '../lib/socket';

export type Role = 'auctioneer' | 'bidder';

export interface User {
  id: string;
  username: string;
  name: string;
  role: Role;
}

export interface RegisterInput {
  username: string;
  password: string;
  role: Role;
}

export interface AuthValue {
  user: User | null;
  token: string | null;
  /** Verdadeiro enquanto o token salvo é conferido em /me. */
  loading: boolean;
  login(username: string, password: string): Promise<User>;
  register(input: RegisterInput): Promise<User>;
  logout(): void;
}

export const AuthContext = createContext<AuthValue | null>(null);

const STORAGE_KEY = 'leilao.token';

// D-16: o token fica no localStorage; o acesso pode falhar (modo privado, bloqueio).
function readToken(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeToken(token: string | null) {
  try {
    if (token) localStorage.setItem(STORAGE_KEY, token);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // sem storage: a sessão dura até fechar a aba
  }
}

/** Página inicial de cada papel depois de entrar (spec 002, cenário 1.1). */
export function homeFor(role: Role): string {
  return role === 'auctioneer' ? '/painel' : '/';
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => readToken());
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(() => token !== null);

  const apply = useCallback((next: string | null, nextUser: User | null) => {
    setAuthToken(next);
    setSocketToken(next);
    writeToken(next);
    setToken(next);
    setUser(nextUser);
  }, []);

  useEffect(() => {
    if (!token || user) return;
    setAuthToken(token);
    setSocketToken(token);
    let alive = true;
    api<{ user: User }>('/me')
      .then(({ user: me }) => alive && setUser(me))
      .catch((err) => {
        // Token vencido ou de antes da 002 (sem papel): volta a visitante.
        if (alive && err instanceof ApiError && err.status === 401) apply(null, null);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [token, user, apply]);

  const value = useMemo<AuthValue>(
    () => ({
      user,
      token,
      loading,
      async login(username, password) {
        const res = await api<{ token: string; user: User }>('/auth/login', { body: { username, password } });
        apply(res.token, res.user);
        setLoading(false);
        return res.user;
      },
      async register(input) {
        const res = await api<{ token: string; user: User }>('/auth/register', { body: input });
        apply(res.token, res.user);
        setLoading(false);
        return res.user;
      },
      logout() {
        apply(null, null);
      },
    }),
    [user, token, loading, apply],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth fora do AuthProvider');
  return value;
}
