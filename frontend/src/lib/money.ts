/**
 * Dinheiro em centavos inteiros (Const. 1.1). Formatação e leitura por
 * manipulação de texto: nenhum passo usa ponto flutuante.
 */
export function formatBRL(cents: number): string {
  const sign = cents < 0 ? '-' : '';
  const digits = String(Math.abs(Math.trunc(cents))).padStart(3, '0');
  const reais = digits.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `${sign}R$ ${reais},${digits.slice(-2)}`;
}

/** "1.234,56" → 123456; "250" → 25000. Vazio, negativo, mais de 2 casas ou lixo → null. */
export function parseBRLToCents(text: string): number | null {
  const clean = text.replace(/R\$/i, '').replace(/\s/g, '');
  const match = /^(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?$/.exec(clean);
  if (!match) return null;
  const reais = match[1]!.replaceAll('.', '').replace(/^0+(?=\d)/, '');
  const cents = Number(`${reais}${(match[2] ?? '').padEnd(2, '0')}`);
  return Number.isSafeInteger(cents) ? cents : null;
}
