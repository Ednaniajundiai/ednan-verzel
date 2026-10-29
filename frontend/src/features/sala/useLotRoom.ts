import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../../api/client';
import { withClock } from '../../lib/clock';
import { getSocket } from '../../lib/socket';
import { applyBid, viewerStatus } from '../lots/standings';
import type { BidPlacedPayload, LotDetail, LotExtendedPayload, LotSettledPayload } from '../lots/types';

/** Aplica um `bid:placed` ao estado da sala (pura; ignora lance repetido). */
export function applyBidEvent(lot: LotDetail, e: BidPlacedPayload): LotDetail {
  if (lot.bids.some((b) => b.id === e.bid_id)) return lot;
  const standings = applyBid(lot.standings, e.bidder, e.amount_cents);
  const viewer = lot.viewer ? { ...lot.viewer, ...viewerStatus(standings, lot.viewer.bidder) } : undefined;
  return {
    ...lot,
    current_price_cents: e.amount_cents,
    next_minimum_cents: e.amount_cents + lot.min_increment_cents,
    bid_count: e.bid_count,
    leader: e.bidder,
    you_are_leading: viewer?.leading ?? false,
    ends_at: e.ends_at,
    extended: Date.parse(e.ends_at) > Date.parse(lot.original_ends_at),
    standings,
    viewer,
    bids: [{ id: e.bid_id, bidder: e.bidder, amount_cents: e.amount_cents, at: e.at }, ...lot.bids].slice(0, 50),
  };
}

const MAX_CONFIRM_RETRIES = 5;

/**
 * Estado da sala: carga com correção do relógio, eventos ao vivo da sala
 * `lot:<id>` e nova carga ao reconectar e ao zerar a contagem (FR-013, FR-017).
 */
export function useLotRoom(lotId: string) {
  const [lot, setLot] = useState<LotDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [extendedAt, setExtendedAt] = useState<string | null>(null);
  const retries = useRef(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const reload = useCallback(async () => {
    try {
      const res = await withClock(() => api<{ server_now: string; lot: LotDetail }>(`/lots/${lotId}`));
      setLot(res.lot);
      setError(null);
      return res.lot;
    } catch (err) {
      setError(
        err instanceof ApiError && (err.status === 404 || err.status === 400)
          ? 'Lote não encontrado.'
          : 'Não foi possível carregar o lote. Tentando de novo…',
      );
      return null;
    }
  }, [lotId]);

  /** Contagem zerou: o servidor confirma a nova fase (Const. 3.1). */
  const confirmPhase = useCallback(async () => {
    const before = lot?.phase;
    const next = await reload();
    if (next && next.phase === before && (next.phase === 'live' || next.phase === 'scheduled') && retries.current < MAX_CONFIRM_RETRIES) {
      retries.current++;
      retryTimer.current = setTimeout(() => void confirmPhase(), 1_000);
    } else {
      retries.current = 0;
    }
  }, [lot?.phase, reload]);

  useEffect(() => {
    void reload();
    return () => {
      if (retryTimer.current) clearTimeout(retryTimer.current);
    };
  }, [reload]);

  useEffect(() => {
    const s = getSocket();
    const join = () => s.emit('lot:join', lotId);
    const mine = (e: { lot_id: string }) => e.lot_id === lotId;
    const onConnect = () => {
      join();
      void reload();
    };
    const onBid = (e: BidPlacedPayload) => mine(e) && setLot((prev) => (prev ? applyBidEvent(prev, e) : prev));
    const onExtended = (e: LotExtendedPayload) => {
      if (!mine(e)) return;
      setLot((prev) => (prev ? { ...prev, ends_at: e.ends_at, extended: true } : prev));
      setExtendedAt(e.ends_at);
    };
    const onSettled = (e: LotSettledPayload) => {
      if (!mine(e)) return;
      setLot((prev) =>
        prev
          ? {
              ...prev,
              status: e.status,
              phase: 'ended',
              result: e.status === 'settled' ? 'sold' : 'unsold',
              current_price_cents: e.final_price_cents ?? prev.current_price_cents,
              leader: e.winner,
              settled_at: e.at,
            }
          : prev,
      );
    };
    const onCancelled = (e: { lot_id: string }) =>
      mine(e) && setLot((prev) => (prev ? { ...prev, status: 'cancelled', phase: 'cancelled' } : prev));

    if (s.connected) join();
    s.on('connect', onConnect);
    s.on('bid:placed', onBid);
    s.on('lot:extended', onExtended);
    s.on('lot:settled', onSettled);
    s.on('lot:cancelled', onCancelled);
    return () => {
      s.emit('lot:leave', lotId);
      s.off('connect', onConnect);
      s.off('bid:placed', onBid);
      s.off('lot:extended', onExtended);
      s.off('lot:settled', onSettled);
      s.off('lot:cancelled', onCancelled);
    };
  }, [lotId, reload]);

  return { lot, error, extendedAt, reload, confirmPhase };
}
