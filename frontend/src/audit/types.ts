export interface AuditEntry {
  lot_id: string;
  seq: number;
  event_type: string;
  payload_canonical: string;
  prev_hash: string;
  hash: string;
  signature: string;
}

export interface WitnessEntry {
  lot_id: string;
  seq: number;
  head_hash: string;
  at: string;
  sig: string;
}

export type FailureKind = 'altered' | 'inserted' | 'missing' | 'truncated' | 'state_mismatch';

export interface ServerVerdict {
  valid: boolean;
  verdict: 'intact' | 'tampered';
  failure_kind: FailureKind | null;
  broken_at_seq: number | null;
  failure_reason: string | null;
  witness_ok: boolean | null;
  head_matches_lot: boolean;
  ends_at_mismatch: boolean;
}

export interface AuditLot {
  id: string;
  title: string;
  image_url: string | null;
  attributes: Record<string, string>;
  size: string | null;
  condition: string | null;
  status: 'open' | 'settled' | 'unsold' | 'cancelled';
  phase: 'scheduled' | 'live' | 'ended' | 'cancelled';
  starts_at: string;
  ends_at: string;
  starting_price_cents: number;
  current_price_cents: number | null;
  bid_count: number;
  audit_head_hash: string;
}

export interface AuditResponse {
  lot_id: string;
  algorithm: string;
  entries: AuditEntry[];
  lot: AuditLot;
  witness: WitnessEntry | null;
  verdict: ServerVerdict;
}

export const FAILURE_LABEL: Record<FailureKind, string> = {
  altered: 'conteúdo alterado',
  missing: 'evento ausente',
  inserted: 'evento intruso',
  truncated: 'fim do histórico removido',
  state_mismatch: 'estado do lote diverge do histórico',
};
