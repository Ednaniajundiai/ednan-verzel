/** Posição do usuário entre os licitantes (FR-011). */
export function StandingBanner({ position, total }: { position: number | null; total: number }) {
  return (
    <p className="standing">
      {position === null ? 'Você ainda não deu lance' : `Você está em ${position}º de ${total} licitantes`}
    </p>
  );
}
