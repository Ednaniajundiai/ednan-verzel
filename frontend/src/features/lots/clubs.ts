import { normalizeText } from '../../lib/text';

export type ClubGroup = 'serie_a' | 'internacional';

export interface Club {
  code: string;
  name: string;
  /** Sigla do escudo genérico, quando falta o arquivo. */
  short: string;
  group: ClubGroup;
  /** Cor de fundo e de contorno do escudo genérico. */
  colors: [string, string];
  /** Outras grafias do nome, inclusive a da TheSportsDB (`attributes.team` do lote). */
  aliases: string[];
}

/** Os 20 da Série A 2026 e 10 internacionais (spec 006). */
export const CLUBS: Club[] = [
  { code: 'athletico-pr', name: 'Athletico-PR', short: 'CAP', group: 'serie_a', colors: ['#c8102e', '#111111'], aliases: ['Athletico Paranaense', 'Atletico Paranaense', 'Athletico', 'Club Athletico Paranaense'] },
  { code: 'atletico-mg', name: 'Atlético-MG', short: 'CAM', group: 'serie_a', colors: ['#111111', '#ffffff'], aliases: ['Atlético Mineiro', 'Clube Atlético Mineiro'] },
  { code: 'bahia', name: 'Bahia', short: 'BAH', group: 'serie_a', colors: ['#0b3a8c', '#e30613'], aliases: ['EC Bahia', 'Esporte Clube Bahia'] },
  { code: 'botafogo', name: 'Botafogo', short: 'BOT', group: 'serie_a', colors: ['#111111', '#ffffff'], aliases: ['Botafogo RJ', 'Botafogo FR'] },
  { code: 'bragantino', name: 'Bragantino', short: 'RBB', group: 'serie_a', colors: ['#d71920', '#ffffff'], aliases: ['Red Bull Bragantino', 'RB Bragantino'] },
  { code: 'chapecoense', name: 'Chapecoense', short: 'CHA', group: 'serie_a', colors: ['#00843d', '#ffffff'], aliases: ['Chapecoense-SC', 'Associação Chapecoense de Futebol'] },
  { code: 'corinthians', name: 'Corinthians', short: 'COR', group: 'serie_a', colors: ['#111111', '#ffffff'], aliases: ['SC Corinthians', 'Sport Club Corinthians Paulista'] },
  { code: 'coritiba', name: 'Coritiba', short: 'CFC', group: 'serie_a', colors: ['#00573f', '#ffffff'], aliases: ['Coritiba FC'] },
  { code: 'cruzeiro', name: 'Cruzeiro', short: 'CRU', group: 'serie_a', colors: ['#1b3f8f', '#ffffff'], aliases: ['Cruzeiro EC'] },
  { code: 'flamengo', name: 'Flamengo', short: 'FLA', group: 'serie_a', colors: ['#c8102e', '#111111'], aliases: ['CR Flamengo', 'Clube de Regatas do Flamengo'] },
  { code: 'fluminense', name: 'Fluminense', short: 'FLU', group: 'serie_a', colors: ['#7a1e3a', '#00613c'], aliases: ['Fluminense FC'] },
  { code: 'gremio', name: 'Grêmio', short: 'GRE', group: 'serie_a', colors: ['#0d80bf', '#111111'], aliases: ['Grêmio FBPA'] },
  { code: 'internacional', name: 'Internacional', short: 'INT', group: 'serie_a', colors: ['#d50032', '#ffffff'], aliases: ['SC Internacional', 'Inter de Porto Alegre'] },
  { code: 'mirassol', name: 'Mirassol', short: 'MIR', group: 'serie_a', colors: ['#f5d200', '#0b6b3a'], aliases: ['Mirassol FC'] },
  { code: 'palmeiras', name: 'Palmeiras', short: 'PAL', group: 'serie_a', colors: ['#006437', '#ffffff'], aliases: ['SE Palmeiras'] },
  { code: 'remo', name: 'Remo', short: 'REM', group: 'serie_a', colors: ['#0a2d6e', '#ffffff'], aliases: ['Clube do Remo'] },
  { code: 'santos', name: 'Santos', short: 'SAN', group: 'serie_a', colors: ['#ffffff', '#111111'], aliases: ['Santos FC'] },
  { code: 'sao-paulo', name: 'São Paulo', short: 'SPF', group: 'serie_a', colors: ['#ffffff', '#d71920'], aliases: ['São Paulo FC'] },
  { code: 'vasco', name: 'Vasco', short: 'VAS', group: 'serie_a', colors: ['#111111', '#ffffff'], aliases: ['Vasco da Gama', 'CR Vasco da Gama'] },
  { code: 'vitoria', name: 'Vitória', short: 'VIT', group: 'serie_a', colors: ['#d71920', '#111111'], aliases: ['EC Vitória'] },
  { code: 'real-madrid', name: 'Real Madrid', short: 'RMA', group: 'internacional', colors: ['#ffffff', '#febe10'], aliases: ['Real Madrid CF'] },
  { code: 'barcelona', name: 'Barcelona', short: 'BAR', group: 'internacional', colors: ['#a50044', '#004d98'], aliases: ['FC Barcelona'] },
  { code: 'manchester-united', name: 'Manchester United', short: 'MUN', group: 'internacional', colors: ['#da291c', '#111111'], aliases: ['Man United', 'Man Utd'] },
  { code: 'liverpool', name: 'Liverpool', short: 'LIV', group: 'internacional', colors: ['#c8102e', '#00b2a9'], aliases: ['Liverpool FC'] },
  { code: 'milan', name: 'Milan', short: 'MIL', group: 'internacional', colors: ['#d01e2f', '#111111'], aliases: ['AC Milan'] },
  { code: 'juventus', name: 'Juventus', short: 'JUV', group: 'internacional', colors: ['#111111', '#ffffff'], aliases: ['Juventus FC'] },
  { code: 'bayern', name: 'Bayern de Munique', short: 'FCB', group: 'internacional', colors: ['#dc052d', '#0066b2'], aliases: ['Bayern Munich', 'Bayern München', 'FC Bayern'] },
  { code: 'psg', name: 'Paris Saint-Germain', short: 'PSG', group: 'internacional', colors: ['#004170', '#da291c'], aliases: ['Paris SG', 'PSG'] },
  { code: 'boca-juniors', name: 'Boca Juniors', short: 'BOC', group: 'internacional', colors: ['#103f79', '#f3b229'], aliases: [] },
  { code: 'river-plate', name: 'River Plate', short: 'RIV', group: 'internacional', colors: ['#ffffff', '#d71920'], aliases: [] },
];

// Igualdade exata depois de normalizar: "Inter Milan" nunca vira Internacional.
const BY_NAME = new Map(CLUBS.flatMap((c) => [c.name, ...c.aliases].map((n) => [normalizeText(n), c] as const)));

/** Clube de um nome de time, ou `null` se não for um dos 30. */
export function clubOf(team: string | null | undefined): Club | null {
  return team ? (BY_NAME.get(normalizeText(team)) ?? null) : null;
}

export function crestUrl(club: Club): string {
  return `/escudos/${club.code}.png`;
}
