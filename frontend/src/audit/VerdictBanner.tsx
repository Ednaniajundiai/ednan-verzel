import { FAILURE_LABEL, type ServerVerdict } from './types';

/** Veredito em destaque (FR-003, FR-004). */
export function VerdictBanner({ verdict }: { verdict: ServerVerdict }) {
  const intact = verdict.verdict === 'intact';
  return (
    <div className={`verdict ${intact ? 'intact' : 'tampered'}`} data-testid="verdict" role="status">
      <strong className="verdict-title">{intact ? '✔ Íntegro' : '✖ Adulterado'}</strong>
      {intact ? (
        <span>
          Todos os eventos conferem com a assinatura da casa.
          {verdict.witness_ok === true && ' O último evento bate com a testemunha guardada fora do banco.'}
          {verdict.witness_ok === null && ' (Sem testemunha externa para este lote.)'}
        </span>
      ) : (
        <span>
          {verdict.broken_at_seq !== null ? `A verificação falhou no evento ${verdict.broken_at_seq}. ` : 'A verificação falhou. '}
          {verdict.failure_kind && `Provável causa: ${FAILURE_LABEL[verdict.failure_kind]}.`}
          {verdict.failure_reason && <span className="muted"> ({verdict.failure_reason})</span>}
        </span>
      )}
    </div>
  );
}
