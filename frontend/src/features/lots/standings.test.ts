import { describe, expect, it } from 'vitest';
import { applyBid, viewerStatus } from './standings';

const s = (bidder: string, max_cents: number) => ({ bidder, max_cents });

describe('posição e indicador (FR-011, FR-012)', () => {
  it('aplicar um lance atualiza o maior lance do pseudônimo e reordena', () => {
    const before = [s('aaa', 300), s('bbb', 200), s('ccc', 100)];
    expect(applyBid(before, 'ccc', 400)).toEqual([s('ccc', 400), s('aaa', 300), s('bbb', 200)]);
    expect(applyBid(before, 'ddd', 350)).toEqual([s('ddd', 350), s('aaa', 300), s('bbb', 200), s('ccc', 100)]);
    expect(before).toHaveLength(3); // não muta
  });

  it('posição "2º de 5" e liderança', () => {
    const st = [s('a', 500), s('me', 400), s('c', 300), s('d', 200), s('e', 100)];
    expect(viewerStatus(st, 'me')).toEqual({ has_bid: true, position: 2, total_bidders: 5, leading: false });
    expect(viewerStatus(st, 'a')).toMatchObject({ position: 1, leading: true });
  });

  it('leading vira falso quando outro pseudônimo dá lance maior', () => {
    let st = [s('me', 200), s('x', 100)];
    expect(viewerStatus(st, 'me').leading).toBe(true);
    st = applyBid(st, 'x', 300);
    expect(viewerStatus(st, 'me')).toMatchObject({ leading: false, position: 2 });
  });

  it('usuário sem lance → has_bid falso', () => {
    expect(viewerStatus([s('a', 1)], 'me')).toEqual({ has_bid: false, position: null, total_bidders: 1, leading: false });
  });
});
