import { afterEach, describe, expect, it, vi } from 'vitest';
import { jsonResponse } from '../test/utils';
import { api, ApiError } from './client';

afterEach(() => vi.unstubAllGlobals());

describe('erro tipado da API (FR-016)', () => {
  it('converte { error: { code, message, ... } } em ApiError com os detalhes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ error: { code: 'BID_TOO_LOW', message: 'Lance abaixo do mínimo', minimum_cents: 1_100 } }, 422)),
    );
    const err = await api('/lots/x/bids', { body: { amount_cents: 1 } }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: 'BID_TOO_LOW', message: 'Lance abaixo do mínimo', status: 422, details: { minimum_cents: 1_100 } });
  });

  it('falha de rede vira NETWORK, sem texto técnico', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('fetch failed'))));
    const err = (await api('/lots').catch((e: unknown) => e)) as ApiError;
    expect(err).toMatchObject({ code: 'NETWORK', status: 0 });
    expect(err.message).not.toMatch(/fetch failed/);
  });
});
