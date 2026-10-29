import { describe, expect, it } from 'vitest';
import css from '../styles.css?raw';

/** Variáveis de um bloco do CSS (`:root {` ou `[data-theme='dark'] {`). */
function vars(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  expect(start).toBeGreaterThanOrEqual(0);
  const block = css.slice(start, css.indexOf('}', start));
  return Object.fromEntries([...block.matchAll(/(--[\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1]!, m[2]!.toLowerCase()]));
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

// Pares texto/fundo usados nas telas, inclusive os selos "íntegro" e "adulterado".
const PAIRS: [string, string][] = [
  ['--text', '--bg'],
  ['--text', '--surface'],
  ['--text', '--surface-alt'],
  ['--muted', '--bg'],
  ['--muted', '--surface'],
  ['--muted', '--surface-alt'],
  ['--primary', '--surface'],
  ['--primary', '--bg'],
  ['--primary', '--primary-soft'],
  ['--primary-text', '--primary'],
  ['--danger', '--danger-soft'],
  ['--danger', '--surface'],
  ['--success', '--success-soft'],
  ['--warning', '--warning-soft'],
];

describe('contraste AA nos dois temas (FR-028, SC-008)', () => {
  for (const theme of [':root', "[data-theme='dark']"]) {
    it(`${theme}: todos os pares ≥ 4,5:1`, () => {
      const v = { ...vars(':root'), ...vars(theme) };
      for (const [fg, bg] of PAIRS) {
        const ratio = contrast(v[fg]!, v[bg]!);
        expect(ratio, `${theme} ${fg} sobre ${bg} = ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(4.5);
      }
    });
  }
});
