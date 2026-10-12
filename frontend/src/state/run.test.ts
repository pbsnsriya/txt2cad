import { describe, expect, it } from 'vitest';
import type { RunEvent } from '../api/client';
import { reduceRun, startRun } from './run';

const ev = (stage: string, message = '', data: Record<string, unknown> = {}, t = 0): RunEvent => ({ seq: 0, t, stage, message, data });

describe('reduceRun', () => {
  it('groups accepted steps by phase and keeps their reasoning', () => {
    let r = startRun('a house');
    r = reduceRun(r, ev('step', 'Ground floor added', { ok: true, phase: 'Massing', why: 'storey stack' }));
    r = reduceRun(r, ev('step', 'Kitchen on L1: 4 x 4 m', { ok: true, phase: 'Floor plates' }));
    r = reduceRun(r, ev('step', 'Hall on L1', { ok: true, phase: 'Floor plates' }));
    expect(r.phases.map((p) => [p.name, p.steps.length])).toEqual([['Massing', 1], ['Floor plates', 2]]);
    expect(r.phases[0].steps[0].why).toBe('storey stack');
  });

  it('shows a rejected step under the latest phase and clears the draft line', () => {
    let r = startRun('x');
    r = reduceRun(r, ev('step', 'Kitchen', { ok: true, phase: 'Floor plates' }));
    r = reduceRun(r, ev('draft', '', { text: 'window kitchen' }));
    expect(r.draft).toBe('window kitchen');
    r = reduceRun(r, ev('step', "window: wall 'north' is interior", { ok: false }));
    expect(r.draft).toBe('');
    expect(r.phases[0].errors).toEqual(["window: wall 'north' is interior"]);
  });

  it('ends in done with the summary, or in error with the message', () => {
    const done = reduceRun(startRun('x'), ev('done', 'Version 1: ok', { number: 1, elements: 54, ifc_url: '/api/x' }));
    expect(done).toMatchObject({ status: 'done', number: 1, elements: 54, summary: 'Version 1: ok' });
    expect(reduceRun(startRun('x'), ev('error', 'no model'))).toMatchObject({ status: 'error', error: 'no model' });
  });

  it('does not mutate the previous state', () => {
    const before = startRun('x');
    const frozen = JSON.stringify(before);
    reduceRun(before, ev('step', 'a', { ok: true, phase: 'Massing' }));
    expect(JSON.stringify(before)).toBe(frozen);
  });
});
