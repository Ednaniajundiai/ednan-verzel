import { useEffect, useRef } from 'react';
import { getSocket } from './socket';

const PRIVATE_EVENTS = ['bid:outbid', 'lot:won', 'wallet:changed'] as const;
const LOT_EVENTS = ['bid:placed', 'lot:settled', 'lot:extended', 'lot:cancelled'] as const;
const WINDOW_MS = 250;

/**
 * Relê os dados da tela quando chega um evento que pode tê-los mudado (spec 004,
 * D-04 e S-19): os privados do usuário sempre; os públicos só de lote observado.
 * Rajadas viram uma leitura a cada 250 ms; reconectar também relê.
 */
export function useLiveRefresh(refresh: () => void, watchedLotIds: string[]): void {
  const refreshRef = useRef(refresh);
  const watched = useRef(new Set(watchedLotIds));
  refreshRef.current = refresh;
  watched.current = new Set(watchedLotIds);

  useEffect(() => {
    const s = getSocket();
    let timer: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      if (timer) return;
      timer = setTimeout(() => {
        timer = null;
        refreshRef.current();
      }, WINDOW_MS);
    };
    const onLot = (e: { lot_id?: string } | undefined) => {
      if (e?.lot_id && watched.current.has(e.lot_id)) schedule();
    };
    PRIVATE_EVENTS.forEach((n) => s.on(n, schedule));
    LOT_EVENTS.forEach((n) => s.on(n, onLot));
    s.on('connect', schedule);
    return () => {
      if (timer) clearTimeout(timer);
      PRIVATE_EVENTS.forEach((n) => s.off(n, schedule));
      LOT_EVENTS.forEach((n) => s.off(n, onLot));
      s.off('connect', schedule);
    };
  }, []);
}
