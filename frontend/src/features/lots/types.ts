import type { Phase } from './phase';
import type { Standing } from './standings';

/** Lote como a API pública devolve (`GET /lots`, `GET /lots/:id`). */
export interface PublicLot {
  id: string;
  item: {
    id: string;
    title: string;
    description: string;
    image_url: string | null;
    size: string | null;
    condition: string | null;
    attributes: Record<string, string>;
  };
  status: 'open' | 'settled' | 'unsold' | 'cancelled';
  phase: Phase;
  result: 'sold' | 'unsold' | null;
  starting_price_cents: number;
  min_increment_cents: number;
  current_price_cents: number | null;
  next_minimum_cents: number;
  leader: string | null;
  you_are_leading: boolean;
  bid_count: number;
  starts_at: string;
  ends_at: string;
  original_ends_at: string;
  extended: boolean;
  settled_at: string | null;
  audit_head_hash: string;
}

export interface BidEntry {
  id: number;
  bidder: string;
  amount_cents: number;
  at: string;
}

export interface LotDetail extends PublicLot {
  standings: Standing[];
  viewer?: { bidder: string; has_bid: boolean; position: number | null; total_bidders: number; leading: boolean };
  bids: BidEntry[];
}

/** Eventos do Socket.IO (só pseudônimos). */
export interface BidPlacedPayload {
  lot_id: string;
  bid_id: number;
  bidder: string;
  amount_cents: number;
  bid_count: number;
  at: string;
  ends_at: string;
}
export interface LotExtendedPayload {
  lot_id: string;
  ends_at: string;
  previous_ends_at: string;
}
export interface LotSettledPayload {
  lot_id: string;
  status: 'settled' | 'unsold';
  winner: string | null;
  final_price_cents: number | null;
  at: string;
}
