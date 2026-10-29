import { afterEach, describe, expect, it, vi } from 'vitest';
import { checkLocalWitness, rememberHead } from './localWitness';

afterEach(() => vi.restoreAllMocks());

const entries = (n: number) => Array.from({ length: n }, (_, i) => ({ seq: i + 1, hash: `h${i + 1}` }));

describe('testemunha do navegador (FR-005, S-06)', () => {
  it('guarda o último {seq, head_hash} visto por lote', () => {
    rememberHead('L1', 3, 'h3');
    expect(checkLocalWitness('L1', entries(3))).toEqual({ seen: { seq: 3, head_hash: 'h3' }, missing: false });
    rememberHead('L1', 2, 'h2'); // nunca recua
    expect(checkLocalWitness('L1', entries(3)).seen).toEqual({ seq: 3, head_hash: 'h3' });
  });

  it('avisa quando a cadeia não contém mais o elo visto', () => {
    rememberHead('L2', 4, 'h4');
    expect(checkLocalWitness('L2', entries(3))).toEqual({ seen: { seq: 4, head_hash: 'h4' }, missing: true });
    expect(checkLocalWitness('L2', [...entries(3), { seq: 4, hash: 'outro' }]).missing).toBe(true);
  });

  it('lote nunca visto: sem testemunha local', () => {
    expect(checkLocalWitness('L9', entries(2))).toEqual({ seen: null, missing: false });
  });

  it('localStorage indisponível não quebra', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    expect(() => rememberHead('L3', 1, 'h1')).not.toThrow();
    expect(checkLocalWitness('L3', entries(1))).toEqual({ seen: null, missing: false });
  });
});
