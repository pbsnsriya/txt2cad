import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, detailText, runPrompt } from './client';

function sseResponse(chunks: string[]): Response {
  const enc = new TextEncoder();
  return new Response(new ReadableStream({ start(c) { chunks.forEach((x) => c.enqueue(enc.encode(x))); c.close(); } }), { status: 200 });
}
const frame = (stage: string, seq: number) => `event: ${stage}\ndata: ${JSON.stringify({ seq, t: 0, stage, message: stage, data: {} })}\n\n`;

afterEach(() => vi.unstubAllGlobals());

describe('runPrompt', () => {
  it('parses events split across network chunks and skips ping comments', async () => {
    const a = frame('build', 1), b = frame('done', 2);
    vi.stubGlobal('fetch', vi.fn(async () => sseResponse([a.slice(0, 20), a.slice(20) + ': ping\n\n' + b.slice(0, 10), b.slice(10)])));
    const got: string[] = [];
    for await (const e of runPrompt('p', { prompt: 'x' }, new AbortController().signal)) got.push(e.stage);
    expect(got).toEqual(['build', 'done']);
  });

  it('turns a 409 into an ApiError with the server message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'project is at version 3' }), { status: 409 })));
    await expect((async () => { for await (const _ of runPrompt('p', { prompt: 'x' }, new AbortController().signal)) { /* none */ } })())
      .rejects.toMatchObject({ status: 409, message: 'project is at version 3' });
  });

  it('explains an unreachable backend', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('failed to fetch'); }));
    await expect((async () => { for await (const _ of runPrompt('p', { prompt: 'x' }, new AbortController().signal)) { /* none */ } })())
      .rejects.toBeInstanceOf(ApiError);
  });
});

describe('detailText', () => {
  it('passes a string through, flattens a validation list, and never returns an object', () => {
    expect(detailText('project is at version 3', 'x')).toBe('project is at version 3');
    expect(detailText([{ loc: ['body', 'prompt'], msg: 'String should have at most 8000 characters' }], 'x')).toBe('prompt: String should have at most 8000 characters');
    expect(detailText({ weird: true }, 'fallback')).toBe('fallback');
  });
});
