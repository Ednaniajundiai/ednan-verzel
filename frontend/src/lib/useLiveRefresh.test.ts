import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installFakeSocket } from '../test/fakeSocket';
import { setSocketForTesting } from './socket';
import { useLiveRefresh } from './useLiveRefresh';

let sock: ReturnType<typeof installFakeSocket>;
beforeEach(() => {
  vi.useFakeTimers();
  sock = installFakeSocket();
});
afterEach(() => {
  vi.useRealTimers();
  setSocketForTesting(null);
});

function setup(lots = ['L1']) {
  const refresh = vi.fn();
  renderHook(() => useLiveRefresh(refresh, lots));
  const flush = () => act(() => vi.advanceTimersByTime(300));
  return { refresh, flush };
}

describe('useLiveRefresh (FR-012, FR-016, S-19)', () => {
  it('relê ao receber bid:outbid, lot:won e wallet:changed', () => {
    const { refresh, flush } = setup();
    for (const name of ['bid:outbid', 'lot:won', 'wallet:changed']) {
      sock.fire(name, { lot_id: 'qualquer' });
      flush();
    }
    expect(refresh).toHaveBeenCalledTimes(3);
  });

  it('eventos públicos só de lote observado', () => {
    const { refresh, flush } = setup(['L1']);
    for (const name of ['bid:placed', 'lot:settled', 'lot:extended', 'lot:cancelled']) {
      sock.fire(name, { lot_id: 'outro' });
      flush();
    }
    expect(refresh).not.toHaveBeenCalled();
    for (const name of ['bid:placed', 'lot:settled', 'lot:extended', 'lot:cancelled']) {
      sock.fire(name, { lot_id: 'L1' });
      flush();
    }
    expect(refresh).toHaveBeenCalledTimes(4);
  });

  it('rajada vira uma só leitura em 250 ms', () => {
    const { refresh, flush } = setup();
    sock.fire('wallet:changed', {});
    sock.fire('bid:outbid', {});
    sock.fire('bid:placed', { lot_id: 'L1' });
    expect(refresh).not.toHaveBeenCalled();
    flush();
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('relê ao reconectar o socket', () => {
    const { refresh, flush } = setup();
    sock.drop();
    sock.restore();
    flush();
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
