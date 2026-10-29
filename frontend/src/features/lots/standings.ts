export interface Standing {
  bidder: string;
  max_cents: number;
}

export interface ViewerStatus {
  has_bid: boolean;
  position: number | null;
  total_bidders: number;
  leading: boolean;
}

/** Aplica um lance ao ranking (maior lance por pseudônimo), sem mutar o original. */
export function applyBid(standings: Standing[], bidder: string, amountCents: number): Standing[] {
  const next = standings.filter((x) => x.bidder !== bidder);
  const previous = standings.find((x) => x.bidder === bidder)?.max_cents ?? 0;
  next.push({ bidder, max_cents: Math.max(previous, amountCents) });
  // sort é estável: em empate fica quem já estava antes (chegou primeiro).
  return next.sort((a, b) => b.max_cents - a.max_cents);
}

/** Posição e liderança do usuário a partir do ranking e do próprio pseudônimo (FR-011, FR-012). */
export function viewerStatus(standings: Standing[], viewerBidder: string): ViewerStatus {
  const index = standings.findIndex((x) => x.bidder === viewerBidder);
  return {
    has_bid: index >= 0,
    position: index >= 0 ? index + 1 : null,
    total_bidders: standings.length,
    leading: index === 0,
  };
}
