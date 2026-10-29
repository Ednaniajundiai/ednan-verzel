import { useEffect, useState } from 'react';
import { io, type Socket } from 'socket.io-client';

/**
 * Socket único da aplicação. O servidor só lê o token no handshake, então
 * trocar de sessão reconecta (entra ou sai da sala privada `user:<id>`).
 */
let socket: Socket | null = null;
let currentToken: string | null = null;

export type SocketStatus = 'connected' | 'reconnecting';

export function getSocket(): Socket {
  if (!socket) {
    socket = io({ path: '/socket.io', auth: (cb) => cb(currentToken ? { token: currentToken } : {}) });
  }
  return socket;
}

/** Testes: troca o socket real por um simulado. */
export function setSocketForTesting(fake: Socket | null): void {
  socket = fake;
}

export function setSocketToken(token: string | null): void {
  if (token === currentToken) return;
  currentToken = token;
  if (socket?.connected) {
    socket.disconnect();
    socket.connect();
  }
}

export function useSocketStatus(): SocketStatus {
  const s = getSocket();
  const [status, setStatus] = useState<SocketStatus>(s.connected ? 'connected' : 'reconnecting');
  useEffect(() => {
    const up = () => setStatus('connected');
    const down = () => setStatus('reconnecting');
    s.on('connect', up);
    s.on('disconnect', down);
    s.on('connect_error', down);
    setStatus(s.connected ? 'connected' : 'reconnecting');
    return () => {
      s.off('connect', up);
      s.off('disconnect', down);
      s.off('connect_error', down);
    };
  }, [s]);
  return status;
}
