import type { AuditEntry, FailureKind, WitnessEntry } from './types';

/**
 * Verificação no navegador (spec 004, FR-025, S-01/S-02): refaz a checagem só
 * com o histórico, a chave pública e a testemunha, com Web Crypto — sem usar o
 * veredito do servidor. Mesma regra do `classifyTrail` do back:
 * conteúdo × hash → `altered`; assinatura → `inserted`; sequência → `missing`;
 * testemunha → `truncated`. Com os dados do lote, também a checagem cruzada.
 */
export interface LotSnapshot {
  status: string;
  audit_head_hash: string;
  current_price_cents: number | null;
  bid_count: number;
  ends_at?: string;
}

export type BrowserVerdict =
  | { supported: false }
  | {
      supported: true;
      verdict: 'intact' | 'tampered';
      failure_kind: FailureKind | null;
      broken_at_seq: number | null;
      witness_ok: boolean | null;
    };

const GENESIS = '0'.repeat(64);
const enc = new TextEncoder();
const FINAL: Record<string, string> = { settled: 'lot_settled', unsold: 'lot_unsold', cancelled: 'lot_cancelled' };

function hexToBytes(hex: string): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  try {
    const bin = atob(b64);
    return Uint8Array.from(bin, (c) => c.charCodeAt(0));
  } catch {
    return new Uint8Array(0);
  }
}

function pemToDer(pem: string): Uint8Array<ArrayBuffer> {
  return base64ToBytes(pem.replace(/-----(BEGIN|END) PUBLIC KEY-----/g, '').replace(/\s+/g, ''));
}

async function sha256Hex(subtle: SubtleCrypto, text: string): Promise<string> {
  const digest = new Uint8Array(await subtle.digest('SHA-256', enc.encode(text)));
  return Array.from(digest, (b) => b.toString(16).padStart(2, '0')).join('');
}

export async function verifyInBrowser(
  input: { entries: AuditEntry[]; publicKeyPem: string; witness: WitnessEntry | null; lot?: LotSnapshot },
  subtle: SubtleCrypto | undefined = globalThis.crypto?.subtle,
): Promise<BrowserVerdict> {
  let key: CryptoKey;
  try {
    if (!subtle) throw new Error('sem Web Crypto');
    key = await subtle.importKey('spki', pemToDer(input.publicKeyPem), { name: 'Ed25519' }, false, ['verify']);
  } catch {
    return { supported: false };
  }
  const check = (sig: string, data: Uint8Array<ArrayBuffer>) =>
    subtle!.verify({ name: 'Ed25519' }, key, base64ToBytes(sig), data).catch(() => false);

  const { entries, witness, lot } = input;
  const w =
    witness && (await check(witness.sig, enc.encode(`witness|${witness.lot_id}|${witness.seq}|${witness.head_hash}|${witness.at}`)))
      ? witness
      : null;
  const witnessOk = w ? entries.length >= w.seq && entries[w.seq - 1]?.hash === w.head_hash : null;
  const result = (failure_kind: FailureKind | null, broken_at_seq: number | null, wOk = witnessOk): BrowserVerdict => ({
    supported: true,
    verdict: failure_kind ? 'tampered' : 'intact',
    failure_kind,
    broken_at_seq,
    witness_ok: wOk,
  });

  let prev = GENESIS;
  for (let i = 0; i < entries.length; i++) {
    const e = entries[i]!;
    const hash = await sha256Hex(subtle, `${e.prev_hash}|${e.lot_id}|${e.seq}|${e.event_type}|${e.payload_canonical}`);
    if (hash !== e.hash) return result('altered', e.seq);
    if (!(await check(e.signature, hexToBytes(e.hash)))) return result('inserted', e.seq);
    if (e.seq !== i + 1 || e.prev_hash !== prev) return result('missing', e.seq);
    prev = e.hash;
  }
  if (w && entries.length < w.seq) return result('truncated', entries.length + 1, false);
  if (w && !witnessOk) return result('altered', w.seq, false);

  if (lot) {
    const last = entries.at(-1);
    if (lot.audit_head_hash !== (last?.hash ?? GENESIS)) return result('truncated', entries.length + 1);
    if (FINAL[lot.status] && last?.event_type !== FINAL[lot.status]) return result('truncated', entries.length + 1);
    const bids = entries.filter((e) => e.event_type === 'bid_placed').map((e) => JSON.parse(e.payload_canonical) as { amount_cents: number });
    if (bids.length !== lot.bid_count || (bids.at(-1)?.amount_cents ?? null) !== lot.current_price_cents) {
      return result('state_mismatch', null);
    }
    if (lot.ends_at) {
      let declared: string | null = null;
      for (const e of entries) {
        const p = JSON.parse(e.payload_canonical) as { ends_at?: string; ends_at_after?: string };
        if (e.event_type === 'lot_opened' && p.ends_at) declared = p.ends_at;
        if (e.event_type === 'lot_extended' && p.ends_at_after) declared = p.ends_at_after;
      }
      if (declared && Date.parse(declared) !== Date.parse(lot.ends_at)) return result('state_mismatch', null);
    }
  }
  return result(null, null);
}
