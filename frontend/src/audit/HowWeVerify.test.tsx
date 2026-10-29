import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import fixtures from './__fixtures__/tamper-cases.json';
import { HowWeVerify } from './HowWeVerify';
import type { AuditEntry, WitnessEntry } from './types';

afterEach(() => vi.unstubAllGlobals());

const intact = fixtures.cases[0] as { entries: AuditEntry[]; witness: WitnessEntry | null };
const altered = fixtures.cases[2] as { entries: AuditEntry[]; witness: WitnessEntry | null };

function renderHow(entries: AuditEntry[], witness: WitnessEntry | null, serverVerdict: 'intact' | 'tampered') {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(fixtures.public_key_pem, { headers: { 'content-type': 'text/plain' } })));
  render(<HowWeVerify lotId="L1" entries={entries} witness={witness} serverVerdict={serverVerdict} />);
}

describe('Como verificamos (FR-023, FR-025, FR-026)', () => {
  it('explica a técnica e oferece o download do histórico e da chave pública', () => {
    renderHow(intact.entries, intact.witness, 'intact');
    expect(screen.getByText('Como verificamos')).toBeTruthy();
    expect(document.body.textContent).toMatch(/SHA-256/);
    expect(document.body.textContent).toMatch(/Ed25519/);
    expect(document.body.textContent).toMatch(/alterar.*remover.*inserir/is);
    expect(screen.getByRole('link', { name: /Baixar o histórico/ }).getAttribute('href')).toBe('/api/audit/lots/L1');
    expect(screen.getByRole('link', { name: /Baixar a chave pública/ }).getAttribute('href')).toBe('/api/audit/public-key');
  });

  it('"verificar no meu navegador" mostra o resultado local e diz se coincide com o servidor', async () => {
    renderHow(intact.entries, intact.witness, 'intact');
    await userEvent.click(screen.getByRole('button', { name: 'Verificar no meu navegador' }));
    const result = await screen.findByTestId('browser-verdict');
    expect(result.textContent).toMatch(/íntegro/i);
    expect(result.textContent).toMatch(/coincide com o veredito do servidor/i);
  });

  it('adulterado no navegador também', async () => {
    renderHow(altered.entries, altered.witness, 'tampered');
    await userEvent.click(screen.getByRole('button', { name: 'Verificar no meu navegador' }));
    const result = await screen.findByTestId('browser-verdict');
    expect(result.textContent).toMatch(/adulterado/i);
    expect(result.textContent).toMatch(/evento 3/);
    expect(result.textContent).toMatch(/coincide/i);
  });
});
