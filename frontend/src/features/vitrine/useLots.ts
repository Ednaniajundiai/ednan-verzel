import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { serverNow, withClock } from '../../lib/clock';
import { getSocket } from '../../lib/socket';
import { displayPhase } from '../lots/phase';
import type { BidPlacedPayload, LotExtendedPayload, LotSettledPayload, PublicLot } from '../lots/types';

/**
 * Lista da vitrine (spec 003, H3): eventos da sala `lots` e mudança de seção pelo
 * relógio corrigido, confirmada por nova carga (o servidor decide a fase).
 */
export function useLots() {
  const [lots, setLots] = useState<PublicLot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loading = useRef(false);
  const lastReload = useRef(0);

  const reload = useCallback(async () => {
    if (loading.current) return;
    loading.current = true;
    lastReload.current = Date.now();
    try {
      const res = await withClock(() => api<{ server_now: string; lots: PublicLot[] }>('/lots'));
      setLots(res.lots.filter((l) => l.phase !== 'cancelled'));
      setError(null);
    } catch {
      setError('Não foi possível carregar os lotes. Tentando de novo…');
    } finally {
      loading.current = false;
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // A cada segundo: algum lote passou de um marco? Pede ao servidor (no máximo 1 carga/s).
  useEffect(() => {
    const timer = setInterval(() => {
      if (!lots || Date.now() - lastReload.current < 1_000) return;
      const now = serverNow();
      if (lots.some((l) => displayPhase(l, now).pending)) void reload();
    }, 250);
    return () => clearInterval(timer);
  }, [lots, reload]);

  useEffect(() => {
    const s = getSocket();
    const update = (id: string, fn: (l: PublicLot) => PublicLot) =>
      setLots((prev) => prev && prev.map((l) => (l.id === id ? fn(l) : l)));
    const onBid = (e: BidPlacedPayload) =>
      update(e.lot_id, (l) => ({
        ...l,
        current_price_cents: e.amount_cents,
        next_minimum_cents: e.amount_cents + l.min_increment_cents,
        bid_count: e.bid_count,
        ends_at: e.ends_at,
      }));
    const onExtended = (e: LotExtendedPayload) => update(e.lot_id, (l) => ({ ...l, ends_at: e.ends_at, extended: true }));
    const onSettled = (e: LotSettledPayload) =>
      update(e.lot_id, (l) => ({
        ...l,
        status: e.status,
        phase: 'ended',
        result: e.status === 'settled' ? 'sold' : 'unsold',
        current_price_cents: e.final_price_cents ?? l.current_price_cents,
      }));
    const onCancelled = (e: { lot_id: string }) => setLots((prev) => prev && prev.filter((l) => l.id !== e.lot_id));
    const onConnect = () => void reload();

    s.on('connect', onConnect);
    s.on('bid:placed', onBid);
    s.on('lot:extended', onExtended);
    s.on('lot:settled', onSettled);
    s.on('lot:cancelled', onCancelled);
    return () => {
      s.off('connect', onConnect);
      s.off('bid:placed', onBid);
      s.off('lot:extended', onExtended);
      s.off('lot:settled', onSettled);
      s.off('lot:cancelled', onCancelled);
    };
  }, [reload]);

  return { lots, error };
}
