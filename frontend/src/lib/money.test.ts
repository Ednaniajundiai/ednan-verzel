import { describe, expect, it } from 'vitest';
import { formatBRL, parseBRLToCents } from './money';

describe('dinheiro em centavos (Const. 1.1)', () => {
  it('formata centavos como reais', () => {
    expect(formatBRL(123_450).replace(/\s/g, ' ')).toBe('R$ 1.234,50');
    expect(formatBRL(5).replace(/\s/g, ' ')).toBe('R$ 0,05');
  });

  it('converte texto em reais para centavos sem ponto flutuante', () => {
    expect(parseBRLToCents('1.234,56')).toBe(123_456);
    expect(parseBRLToCents('250')).toBe(25_000);
    expect(parseBRLToCents('0,1')).toBe(10);
    expect(parseBRLToCents('R$ 19,90')).toBe(1_990);
    expect(parseBRLToCents('0,29')).toBe(29);
  });

  it('recusa o que não é um valor válido', () => {
    for (const bad of ['', '  ', 'abc', '1,234', '-5', '1.2.3,4', '12,3,4']) {
      expect(parseBRLToCents(bad)).toBeNull();
    }
  });
});
