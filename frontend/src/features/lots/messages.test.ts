import { describe, expect, it } from 'vitest';
import { bidRefusalMessage } from './messages';

const err = (code: string, details: Record<string, unknown> = {}, message = 'texto do servidor') => ({ code, message, details });

describe('mensagens de recusa de lance (FR-001 a FR-005, FR-025, SC-001)', () => {
  it('sete códigos → sete mensagens distintas, com o dado de apoio', () => {
    const messages = [
      bidRefusalMessage(err('LOT_NOT_STARTED', { starts_at: '2026-10-28T23:30:00.000Z' })),
      bidRefusalMessage(err('LOT_ENDED')),
      bidRefusalMessage(err('LOT_CANCELLED')),
      bidRefusalMessage(err('ALREADY_LEADING')),
      bidRefusalMessage(err('BID_TOO_LOW', { minimum_cents: 11_000 })),
      bidRefusalMessage(err('INSUFFICIENT_FUNDS', { available_cents: 5_000 })),
      bidRefusalMessage(err('AUCTIONEER_CANNOT_BID')),
    ];
    expect(new Set(messages).size).toBe(7);
    const norm = messages.map((m) => m.replace(/\s/g, ' '));
    expect(norm[0]).toMatch(/^Este lote ainda não começou\. Começa em \d{2}\/\d{2}/);
    expect(norm[1]).toBe('Este lote já foi encerrado.');
    expect(norm[2]).toBe('Este lote foi cancelado.');
    expect(norm[3]).toBe('Você já está ganhando este lote.');
    expect(norm[4]).toBe('Lance abaixo do mínimo. O mínimo aceito é R$ 110,00.');
    expect(norm[5]).toBe('Saldo insuficiente. Seu saldo disponível é R$ 50,00.');
    expect(norm[6]).toBe('Leiloeiros não dão lances.');
  });

  it('código desconhecido usa a mensagem do servidor', () => {
    expect(bidRefusalMessage(err('ALGO_NOVO', {}, 'Mensagem nova do servidor'))).toBe('Mensagem nova do servidor');
  });
});
