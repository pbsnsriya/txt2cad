import { describe, expect, it } from 'vitest';
import { footprint, parseMetres, roomChanges, show, sizeProblem } from './sizes';

const rooms = [
  { id: 'living', name: 'Living', level: 'L1', rect: [0, 0, 5, 4] },
  { id: 'kitchen', name: 'Kitchen', level: 'L1', rect: [5, 0, 4, 4] },
  { id: 'bed', name: 'Bedroom', level: 'L2', rect: [0, 0, 4, 4] },
];

describe('parseMetres', () => {
  it('reads plain numbers and a decimal comma', () => {
    expect(parseMetres('5')).toBe(5);
    expect(parseMetres(' 6.5 ')).toBe(6.5);
    expect(parseMetres('6,5')).toBe(6.5);
    expect(parseMetres('.5')).toBe(0.5);
  });
  it('refuses what is not a number', () => {
    for (const t of ['', ' ', 'abc', '1e3', '-4', '5m', '1.2.3', '--']) expect(parseMetres(t)).toBeNull();
  });
});

describe('sizeProblem', () => {
  it('says nothing for an empty box and for a good size', () => {
    expect(sizeProblem('', 'Width')).toBe('');
    expect(sizeProblem('4.5', 'Width')).toBe('');
  });
  it('explains a bad one', () => {
    expect(sizeProblem('x', 'Width')).toContain('number');
    expect(sizeProblem('0.5', 'Width')).toContain('between 1.5 and 40');
    expect(sizeProblem('41', 'Depth')).toContain('between');
  });
});

describe('footprint', () => {
  it('measures the lowest level that has rooms', () => {
    expect(footprint([{ id: 'L1' }, { id: 'L2' }], rooms)).toEqual({ width: 9, depth: 4 });
    expect(footprint([{ id: 'L3' }, { id: 'L2' }], rooms)).toEqual({ width: 4, depth: 4 });
    expect(footprint([{ id: 'L9' }], rooms)).toBeNull();
  });
});

describe('roomChanges', () => {
  it('sends only the sizes that changed', () => {
    expect(roomChanges(rooms, { living: { width: '6', depth: '4' }, kitchen: { width: '4', depth: '4' } })).toEqual([{ room: 'living', width: 6 }]);
    expect(roomChanges(rooms, { living: { width: '5', depth: '4.5' } })).toEqual([{ room: 'living', depth: 4.5 }]);
  });
  it('ignores empty and unreadable boxes', () => {
    expect(roomChanges(rooms, { living: { width: '', depth: 'x' } })).toEqual([]);
    expect(roomChanges(rooms, {})).toEqual([]);
  });
});

describe('show', () => {
  it('trims noise', () => { expect(show(4.000000001)).toBe('4'); expect(show(6.456)).toBe('6.46'); });
});
