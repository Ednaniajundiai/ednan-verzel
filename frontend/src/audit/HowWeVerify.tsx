import { useState } from 'react';
import { FAILURE_LABEL, type AuditEntry, type WitnessEntry } from './types';
import { verifyInBrowser, type BrowserVerdict, type LotSnapshot } from './verify';

/** Explicação curta da técnica, downloads e verificação no navegador (FR-023, FR-025, FR-026). */
export function HowWeVerify({
  lotId,
  entries,
  witness,
  lot,
  serverVerdict,
}: {
  lotId: string;
  entries: AuditEntry[];
  witness: WitnessEntry | null;
  lot?: LotSnapshot;
  serverVerdict: 'intact' | 'tampered';
}) {
  const [result, setResult] = useState<BrowserVerdict | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch('/api/audit/public-key');
      if (!res.ok) throw new Error();
      setResult(await verifyInBrowser({ entries, publicKeyPem: await res.text(), witness, lot }));
    } catch {
      setError('Não foi possível baixar a chave pública agora. Tente de novo.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card stack">
      <details open>
        <summary>
          <strong>Como verificamos</strong>
        </summary>
        <div className="stack how">
          <p>
            Cada evento do lote (abertura, lance, prorrogação, encerramento) entra numa <strong>corrente</strong>: o
            resumo SHA-256 de um evento inclui o resumo do anterior. Mudar qualquer evento muda o resumo dele e
            desencaixa todos os seguintes.
          </p>
          <p>
            Cada resumo é <strong>assinado com Ed25519</strong> pela chave privada da casa, que não fica no banco. Quem
            mexer no banco consegue recalcular resumos, mas não consegue assiná-los.
          </p>
          <p>
            Depois de cada evento, o servidor grava uma <strong>testemunha assinada fora do banco</strong> com o último
            evento do lote, e este navegador também guarda o último que viu. Por isso, apagar o fim do histórico não passa
            despercebido.
          </p>
          <ul>
            <li>
              <strong>alterar</strong> um lance quebra o resumo daquele evento (conteúdo alterado);
            </li>
            <li>
              <strong>remover</strong> um lance do meio deixa um buraco na sequência (evento ausente); remover o último
              contradiz a testemunha (fim removido);
            </li>
            <li>
              <strong>inserir</strong> um lance falso exige uma assinatura que só a casa produz (evento intruso).
            </li>
          </ul>
          <p className="muted">O preço, o líder, a contagem de lances e o fim do lote também são conferidos contra o histórico.</p>
        </div>
      </details>

      <div className="row">
        <a href={`/api/audit/lots/${lotId}`} download={`auditoria-${lotId}.json`}>
          Baixar o histórico (JSON)
        </a>
        <a href="/api/audit/public-key" download="chave-publica-casa.pem">
          Baixar a chave pública
        </a>
        <button type="button" onClick={run} disabled={busy}>
          Verificar no meu navegador
        </button>
      </div>
      <p className="muted">
        Fora do site: <code>uv run --directory backend python -m scripts.verify_audit {lotId} &lt;url-da-api&gt;</code>
      </p>
      {error && <p className="notice error">{error}</p>}
      {result && (
        <div className="notice" data-testid="browser-verdict" role="status">
          {!result.supported ? (
            <span>
              Este navegador não oferece Ed25519 no Web Crypto. Use o verificador offline acima; o veredito do servidor
              continua visível.
            </span>
          ) : (
            <span>
              Verificação no seu navegador: <strong>{result.verdict === 'intact' ? 'íntegro' : 'adulterado'}</strong>
              {result.verdict === 'tampered' && result.broken_at_seq !== null && ` no evento ${result.broken_at_seq}`}
              {result.failure_kind && ` (${FAILURE_LABEL[result.failure_kind]})`}.{' '}
              {result.verdict === serverVerdict ? 'Coincide com o veredito do servidor.' : 'Difere do veredito do servidor.'}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
