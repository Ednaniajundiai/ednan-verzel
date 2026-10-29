import { formatBRL } from '../../lib/money';

export interface RefusalLike {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

const when = (iso: unknown) =>
  typeof iso === 'string'
    ? new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    : '';

/**
 * Texto da recusa de lance (spec 003, D-09): o código decide a mensagem; o
 * dado de apoio vem nos detalhes da API. Código desconhecido usa o texto do servidor.
 */
export function bidRefusalMessage(err: RefusalLike): string {
  const d = err.details ?? {};
  switch (err.code) {
    case 'AUCTIONEER_CANNOT_BID':
      return 'Leiloeiros não dão lances.';
    case 'LOT_CANCELLED':
      return 'Este lote foi cancelado.';
    case 'LOT_NOT_STARTED':
      return `Este lote ainda não começou. Começa em ${when(d.starts_at)}.`;
    case 'LOT_ENDED':
      return 'Este lote já foi encerrado.';
    case 'ALREADY_LEADING':
      return 'Você já está ganhando este lote.';
    case 'BID_TOO_LOW':
      return typeof d.minimum_cents === 'number'
        ? `Lance abaixo do mínimo. O mínimo aceito é ${formatBRL(d.minimum_cents)}.`
        : 'Lance abaixo do mínimo.';
    case 'INSUFFICIENT_FUNDS':
      return typeof d.available_cents === 'number'
        ? `Saldo insuficiente. Seu saldo disponível é ${formatBRL(d.available_cents)}.`
        : 'Saldo insuficiente.';
    default:
      return err.message;
  }
}
