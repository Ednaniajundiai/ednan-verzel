import { describe, expect, it } from 'vitest';
import { CLUBS, clubOf } from './clubs';
import { filterLots } from './filter';

const lots = [
  { id: '1', phase: 'live' as const, item: { title: 'Camisa Flamengo 2019' } },
  { id: '2', phase: 'scheduled' as const, item: { title: 'Camisa Palmeiras 2021' } },
  { id: '3', phase: 'ended' as const, item: { title: 'Camisa São Paulo 2005' } },
];

describe('busca e filtro (FR-024)', () => {
  it('"flamengo" acha o Flamengo e não o Palmeiras', () => {
    expect(filterLots(lots, 'flamengo', 'all').map((l) => l.id)).toEqual(['1']);
  });

  it('sem diferenciar acentos nem maiúsculas', () => {
    expect(filterLots(lots, 'SAO paulo', 'all').map((l) => l.id)).toEqual(['3']);
    expect(filterLots(lots, '  são  ', 'all').map((l) => l.id)).toEqual(['3']);
  });

  it('filtro por fase devolve só a fase escolhida; busca vazia não filtra', () => {
    expect(filterLots(lots, '', 'scheduled').map((l) => l.id)).toEqual(['2']);
    expect(filterLots(lots, '', 'all')).toHaveLength(3);
  });
});

const teamLot = (id: string, phase: 'live' | 'scheduled' | 'ended', title: string, team?: string) => ({
  id,
  phase,
  item: { title, attributes: (team ? { team } : {}) as Record<string, string> },
});

const byTeam = [
  teamLot('fla', 'live', 'Camisa Flamengo 2019', 'Flamengo'),
  teamLot('fla81', 'scheduled', 'Camisa Flamengo 1981', 'Flamengo'),
  teamLot('sp', 'ended', 'Camisa São Paulo 2021', 'Sao Paulo'),
  teamLot('cam', 'live', 'Camisa Galo 2013', 'Atletico Mineiro'),
  teamLot('rbb', 'live', 'Camisa Bragantino 2020', 'Red Bull Bragantino'),
  teamLot('vas', 'ended', 'Camisa Vasco 1998', 'Vasco da Gama'),
  teamLot('int', 'live', 'Camisa Inter 2006', 'Internacional'),
  teamLot('inter-milao', 'live', 'Camisa Inter de Milão 2010', 'Inter Milan'),
  teamLot('sem', 'live', 'Camisa sem clube'),
];
const ids = (club: string | null, query = '', phase: 'all' | 'live' | 'scheduled' | 'ended' = 'all') =>
  filterLots(byTeam, query, phase, club).map((l) => l.id);

describe('lista de clubes (spec 006)', () => {
  it('20 da Série A e 10 internacionais, códigos únicos', () => {
    expect(CLUBS.filter((c) => c.group === 'serie_a')).toHaveLength(20);
    expect(CLUBS.filter((c) => c.group === 'internacional')).toHaveLength(10);
    expect(new Set(CLUBS.map((c) => c.code)).size).toBe(30);
  });

  it('reconhece o clube pelo nome inteiro, sem acento nem maiúsculas', () => {
    expect(clubOf('SÃO PAULO')?.code).toBe('sao-paulo');
    expect(clubOf('Gremio')?.code).toBe('gremio');
    expect(clubOf('Inter Milan')).toBeNull();
    expect(clubOf('Santos Laguna')).toBeNull();
    expect(clubOf(undefined)).toBeNull();
  });
});

describe('filtro por clube (spec 006)', () => {
  it('sem clube escolhido não filtra', () => {
    expect(ids(null)).toHaveLength(byTeam.length);
  });

  it('acha o clube nas grafias da TheSportsDB (cenário 4)', () => {
    expect(ids('flamengo')).toEqual(['fla', 'fla81']);
    expect(ids('sao-paulo')).toEqual(['sp']);
    expect(ids('atletico-mg')).toEqual(['cam']);
    expect(ids('bragantino')).toEqual(['rbb']);
    expect(ids('vasco')).toEqual(['vas']);
  });

  it('Internacional não traz a Inter de Milão (cenário 5)', () => {
    expect(ids('internacional')).toEqual(['int']);
  });

  it('soma com a busca por texto e o estado (cenário 6)', () => {
    expect(ids('flamengo', '2019', 'live')).toEqual(['fla']);
    expect(ids('flamengo', '', 'scheduled')).toEqual(['fla81']);
    expect(ids('flamengo', 'palmeiras')).toEqual([]);
  });
});
