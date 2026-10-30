import { describe, expect, it } from 'vitest';
import type { PublicLot } from '../lots/types';
import { clubCounts, endingSoon, featuredLot, highestBids, mostDisputed } from './highlights';

const T = Date.parse('2026-10-29T20:00:00.000Z');
const at = (min: number) => new Date(T + min * 60_000).toISOString();

function lot(id: string, over: Partial<PublicLot> & { team?: string } = {}): PublicLot {
  const { team, ...rest } = over;
  return {
    id,
    item: { id: `i-${id}`, title: id, description: '', image_url: null, size: null, condition: null, attributes: team ? { team } : {} },
    status: 'open',
    phase: 'live',
    result: null,
    starting_price_cents: 10_000,
    min_increment_cents: 1_000,
    current_price_cents: null,
    next_minimum_cents: 10_000,
    leader: null,
    you_are_leading: false,
    bid_count: 0,
    starts_at: at(-60),
    ends_at: at(30),
    original_ends_at: at(30),
    extended: false,
    settled_at: null,
    audit_head_hash: 'h',
    ...rest,
  };
}

const ids = (lots: PublicLot[]) => lots.map((l) => l.id);

describe('destaques da home (ideia 2)', () => {
  it('destaque: o ao vivo que acaba primeiro; sem ao vivo, o próximo agendado; sem nenhum, o último encerrado', () => {
    const live = [lot('a', { ends_at: at(30) }), lot('b', { ends_at: at(5) })];
    const sched = [lot('c', { phase: 'scheduled', starts_at: at(20) }), lot('d', { phase: 'scheduled', starts_at: at(10) })];
    const ended = [
      lot('e', { phase: 'ended', ends_at: at(-50) }),
      lot('f', { phase: 'ended', ends_at: at(-10), settled_at: at(-10) }),
    ];
    expect(featuredLot([...live, ...sched, ...ended])?.id).toBe('b');
    expect(featuredLot([...sched, ...ended])?.id).toBe('d');
    expect(featuredLot(ended)?.id).toBe('f');
    expect(featuredLot([])).toBeNull();
  });

  it('terminando em breve: ao vivo pelo fim, depois agendados pelo início; nunca encerrados', () => {
    const lots = [
      lot('s', { phase: 'scheduled', starts_at: at(3) }),
      lot('l2', { ends_at: at(40) }),
      lot('l1', { ends_at: at(2) }),
      lot('e', { phase: 'ended' }),
    ];
    expect(ids(endingSoon(lots))).toEqual(['l1', 'l2', 's']);
  });

  it('mais disputadas e maiores lances ignoram lotes sem lance', () => {
    const lots = [
      lot('x', { bid_count: 3, current_price_cents: 19_000 }),
      lot('y', { bid_count: 7, current_price_cents: 15_000 }),
      lot('z'),
    ];
    expect(ids(mostDisputed(lots))).toEqual(['y', 'x']);
    expect(ids(highestBids(lots))).toEqual(['x', 'y']);
  });

  it('conta os lotes de cada clube pelo nome do time', () => {
    const counts = clubCounts([lot('1', { team: 'Flamengo' }), lot('2', { team: 'Flamengo' }), lot('3', { team: 'Sao Paulo' }), lot('4')]);
    expect(counts.get('flamengo')).toBe(2);
    expect(counts.get('sao-paulo')).toBe(1);
    expect(counts.get('palmeiras')).toBeUndefined();
  });
});
