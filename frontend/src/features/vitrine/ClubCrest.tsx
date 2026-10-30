import { useState } from 'react';
import { type Club, crestUrl } from '../lots/clubs';

/** Texto escuro ou claro, conforme o fundo do escudo genérico. */
function inkFor(hex: string): string {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return 0.299 * r! + 0.587 * g! + 0.114 * b! > 150 ? '#111111' : '#ffffff';
}

/** Escudo versionado em `public/escudos/`; sem o arquivo, um escudo genérico com a sigla. */
export function ClubCrest({ club, size = 40, label }: { club: Club; size?: number; label?: string }) {
  const [missing, setMissing] = useState(false);
  const a11y = label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true };

  if (missing) {
    const [fill, stroke] = club.colors;
    return (
      <svg className="crest" width={size} height={size} viewBox="0 0 40 40" {...a11y}>
        <path d="M20 2 L36 7 V19 C36 29 29 35 20 38 C11 35 4 29 4 19 V7 Z" fill={fill} stroke={stroke} strokeWidth="2.5" />
        <text x="20" y="23.5" textAnchor="middle" fontSize="10" fontWeight="700" fill={inkFor(fill)}>
          {club.short}
        </text>
      </svg>
    );
  }
  return (
    <img
      className="crest"
      src={crestUrl(club)}
      width={size}
      height={size}
      alt={label ?? ''}
      loading="lazy"
      onError={() => setMissing(true)}
    />
  );
}
