import { useTheme } from './ThemeProvider';

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === 'dark' ? 'claro' : 'escuro';
  return (
    <button type="button" className="theme-toggle" onClick={toggle} aria-label={`Usar tema ${next}`} title={`Usar tema ${next}`}>
      {theme === 'dark' ? '☀ Tema claro' : '☾ Tema escuro'}
    </button>
  );
}
