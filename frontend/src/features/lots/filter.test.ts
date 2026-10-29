import { describe, expect, it } from 'vitest';
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
