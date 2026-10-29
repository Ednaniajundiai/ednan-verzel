import type { Socket } from 'socket.io-client';
import { act } from '@testing-library/react';
import { setSocketForTesting } from '../lib/socket';

type Handler = (...args: unknown[]) => void;

/** Socket simulado: registra o que o cliente emite e deixa o teste disparar eventos do servidor. */
export function installFakeSocket(connected = true) {
  const handlers = new Map<string, Set<Handler>>();
  const emitted: [string, unknown][] = [];
  const fake = {
    connected,
    on(name: string, fn: Handler) {
      if (!handlers.has(name)) handlers.set(name, new Set());
      handlers.get(name)!.add(fn);
      return fake;
    },
    off(name: string, fn: Handler) {
      handlers.get(name)?.delete(fn);
      return fake;
    },
    emit(name: string, payload: unknown) {
      emitted.push([name, payload]);
      return fake;
    },
    connect() {
      return fake;
    },
    disconnect() {
      return fake;
    },
  };
  setSocketForTesting(fake as unknown as Socket);
  const fire = (name: string, ...args: unknown[]) => act(() => handlers.get(name)?.forEach((fn) => fn(...args)));
  return {
    emitted,
    fire,
    drop: () => {
      fake.connected = false;
      fire('disconnect');
    },
    restore: () => {
      fake.connected = true;
      fire('connect');
    },
  };
}
