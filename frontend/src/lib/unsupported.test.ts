import { describe, expect, it } from 'vitest';
import { findUnsupported } from './unsupported';

const WORDS = { basement: 'a basement', pool: 'a pool', 'swimming pool': 'a pool', balcony: 'a balcony', 'curved wall': 'curved walls', 'curved walls': 'curved walls' };

describe('findUnsupported', () => {
  it('names each thing once, in reading order', () => {
    expect(findUnsupported('A house with a basement, a swimming pool, a pool house, a balcony and a curved wall.', WORDS)).toEqual(['a basement', 'a pool', 'a balcony', 'curved walls']);
  });
  it('says nothing for a request it can build, and matches whole words only', () => {
    expect(findUnsupported('Two storey house with a kitchen', WORDS)).toEqual([]);
    expect(findUnsupported('Poolside cabin', WORDS)).toEqual([]);
    expect(findUnsupported('three balconies', WORDS)).toEqual([]);      // not a listed word form; the checklist after the build still catches it
  });
  it('is not fooled by punctuation in a word list', () => {
    expect(findUnsupported('a (basement)', { '(basement)': 'x' })).toEqual([]);
  });
});
