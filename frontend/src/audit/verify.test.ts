import { describe, expect, it } from 'vitest';
import fixtures from './__fixtures__/tamper-cases.json';
import type { AuditEntry, WitnessEntry } from './types';
import { verifyInBrowser } from './verify';

type Case = { name: string; entries: AuditEntry[]; witness: WitnessEntry | null; expected: Record<string, unknown> };

describe('verificador do navegador nos casos do servidor (FR-025, SC-007)', () => {
  it.each((fixtures.cases as Case[]).map((c) => [c.name, c] as const))('%s', async (_name, c) => {
    const r = await verifyInBrowser({ entries: c.entries, publicKeyPem: fixtures.public_key_pem, witness: c.witness });
    expect(r.supported).toBe(true);
    expect(r).toMatchObject(c.expected);
  });

  it('sem Ed25519 no Web Crypto, devolve "não suportado"', async () => {
    const broken = {
      importKey: async () => {
        throw new Error('NotSupportedError');
      },
      digest: crypto.subtle.digest.bind(crypto.subtle),
      verify: crypto.subtle.verify.bind(crypto.subtle),
    } as unknown as SubtleCrypto;
    const c = fixtures.cases[0] as Case;
    expect(await verifyInBrowser({ entries: c.entries, publicKeyPem: fixtures.public_key_pem, witness: null }, broken)).toEqual({
      supported: false,
    });
  });

  it('com os dados do lote, também confere a cabeça e o evento final', async () => {
    const c = fixtures.cases[0] as Case;
    const last = c.entries.at(-1)!;
    const lot = { status: 'settled', audit_head_hash: last.hash, current_price_cents: 11_000, bid_count: 2, ends_at: '2026-10-28T20:12:00.000Z' };
    expect(await verifyInBrowser({ entries: c.entries, publicKeyPem: fixtures.public_key_pem, witness: null, lot })).toMatchObject({ verdict: 'intact' });
    expect(
      await verifyInBrowser({ entries: c.entries, publicKeyPem: fixtures.public_key_pem, witness: null, lot: { ...lot, current_price_cents: 1 } }),
    ).toMatchObject({ verdict: 'tampered', failure_kind: 'state_mismatch' });
    expect(
      await verifyInBrowser({ entries: c.entries.slice(0, 4), publicKeyPem: fixtures.public_key_pem, witness: null, lot: { ...lot, audit_head_hash: c.entries[3]!.hash } }),
    ).toMatchObject({ verdict: 'tampered', failure_kind: 'truncated' });
  });
});
