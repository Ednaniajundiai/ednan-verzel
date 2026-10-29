import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from './ThemeProvider';
import { ThemeToggle } from './ThemeToggle';

function mockSystem(dark: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((q: string) => ({ matches: dark && q.includes('dark'), media: q, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  delete document.documentElement.dataset.theme;
});

const renderApp = () =>
  render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>,
  );

describe('tema claro e escuro (FR-028)', () => {
  it('primeira visita segue o prefers-color-scheme', () => {
    mockSystem(true);
    renderApp();
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('o botão alterna sem recarregar e a escolha persiste', async () => {
    mockSystem(true);
    const { unmount } = renderApp();
    await userEvent.click(screen.getByRole('button', { name: /tema claro/i }));
    expect(document.documentElement.dataset.theme).toBe('light');
    unmount();
    renderApp(); // "volta depois": vale a escolha, não o sistema
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(screen.getByRole('button', { name: /tema escuro/i })).toBeTruthy();
  });

  it('localStorage indisponível não quebra', async () => {
    mockSystem(false);
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    renderApp();
    expect(document.documentElement.dataset.theme).toBe('light');
    await userEvent.click(screen.getByRole('button', { name: /tema escuro/i }));
    expect(document.documentElement.dataset.theme).toBe('dark');
  });
});
