import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

/**
 * Tema claro e escuro (spec 004, FR-028, S-15): primeira visita segue o
 * sistema; a escolha fica no localStorage. O `index.html` aplica o tema antes
 * da primeira pintura com a mesma regra, para a tela não piscar.
 */
export type Theme = 'light' | 'dark';
const KEY = 'leilao.theme';

interface ThemeValue {
  theme: Theme;
  toggle(): void;
}

const ThemeContext = createContext<ThemeValue>({ theme: 'light', toggle: () => {} });

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    // sem storage: segue o sistema
  }
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = current === 'dark' ? 'light' : 'dark';
      try {
        localStorage.setItem(KEY, next);
      } catch {
        // a escolha vale até fechar a aba
      }
      return next;
    });
  }, []);

  const value = useMemo(() => ({ theme, toggle }), [theme, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  return useContext(ThemeContext);
}
