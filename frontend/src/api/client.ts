/**
 * Cliente da API. Toda chamada vai para `/api`, prefixo que o nginx e o
 * proxy do Vite removem antes de chegar ao Express (D-14 da 002).
 */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /** Erros de validação por campo (`issues` do Zod no servidor). */
  get fieldErrors(): Record<string, string[]> {
    return (this.details.issues as Record<string, string[]> | undefined) ?? {};
  }
}

let authToken: string | null = null;

/** Chamado pelo AuthContext: o token passa a ir em toda requisição. */
export function setAuthToken(token: string | null) {
  authToken = token;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { ...opts.headers };
  if (opts.body !== undefined) headers['content-type'] = 'application/json';
  if (authToken) headers.authorization = `Bearer ${authToken}`;

  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method: opts.method ?? (opts.body === undefined ? 'GET' : 'POST'),
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    throw new ApiError('NETWORK', 'Sem conexão com o servidor. Tente de novo.', 0);
  }

  const body = (await res.json().catch(() => null)) as
    | (T & { error?: { code?: string; message?: string } & Record<string, unknown> })
    | null;
  if (!res.ok) {
    const { code = 'INTERNAL', message = 'Erro inesperado. Tente de novo.', ...details } = body?.error ?? {};
    throw new ApiError(code, message, res.status, details);
  }
  return body as T;
}
