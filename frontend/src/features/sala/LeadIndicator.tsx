/** Indicador fixo e destacado (FR-012). */
export function LeadIndicator({ leading }: { leading: boolean }) {
  return (
    <div className={`lead-indicator ${leading ? 'winning' : 'outbid'}`} role="status" aria-live="polite">
      {leading ? 'Você está ganhando' : 'Você foi superado'}
    </div>
  );
}
