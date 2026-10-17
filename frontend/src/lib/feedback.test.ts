import { describe, expect, it } from 'vitest';
import { buildFeedback, ISSUES_URL } from './feedback';

describe('buildFeedback', () => {
  it('leaves the request and the result out unless asked to include them', () => {
    const f = buildFeedback({ rating: 4, comment: 'The roof was wrong.', include: false, prompt: 'A secret house', summary: 'Version 1: 2 levels' });
    expect(f.body).toContain('4 of 5');
    expect(f.body).toContain('The roof was wrong.');
    expect(f.body).not.toContain('secret');
    expect(decodeURIComponent(f.url)).not.toContain('secret');
    expect(f.url.startsWith(`${ISSUES_URL}?title=`)).toBe(true);
  });
  it('includes them when ticked, quoted, and says why', () => {
    const f = buildFeedback({ rating: 2, comment: 'Not what I asked.', include: true, prompt: 'A house\nwith a pool', summary: 'Version 3: rooms', version: 3 });
    expect(f.body).toContain('> A house\n> with a pool');
    expect(f.body).toContain('version 3');
    expect(f.body).toContain('Included because I ticked the box');
  });
  it('copes with nothing written, no rating, and very long text', () => {
    const empty = buildFeedback({ rating: 0, comment: '', include: false });
    expect(empty.title).toBe('Feedback');
    expect(empty.body).toContain('not rated');
    const long = buildFeedback({ rating: 5, comment: 'x'.repeat(20000), include: false });
    expect(long.body.length).toBeLessThan(5600);
    expect(long.url.length).toBeLessThan(8000);
  });
});
