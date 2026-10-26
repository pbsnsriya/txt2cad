import { describe, expect, it } from 'vitest';
import { cameraOffset, ease, fitDistance, isShown, orthoHeight, roomShown, subtitle, viewById, VIEWS, type Category } from './logic';
import { floats, fromBase64, uints } from './data';

const all = new Set<Category>(['wall', 'floor', 'roof', 'opening', 'stair', 'furniture', 'finish']);

describe('cameraOffset', () => {
  it('stands south of the model at azimuth 0, so north is up in the top view', () => {
    const [x, y, z] = cameraOffset(10, 0, 0);
    expect(x).toBeCloseTo(0); expect(y).toBeCloseTo(0); expect(z).toBeCloseTo(10);
    const top = cameraOffset(10, 0, 89.5);
    expect(top[1]).toBeGreaterThan(9.99); expect(Math.abs(top[0])).toBeLessThan(1e-6);
  });
  it('goes east at 90 degrees and keeps its distance', () => {
    const [x, , z] = cameraOffset(10, 90, 0);
    expect(x).toBeCloseTo(10); expect(z).toBeCloseTo(0, 5);
    for (const v of VIEWS) { const o = cameraOffset(7, v.azimuth, v.elevation); expect(Math.hypot(...o)).toBeCloseTo(7); }
  });
});

describe('views', () => {
  it('has the look-inside view, steeper than the 3D view', () => {
    expect(viewById('inside').elevation).toBeGreaterThan(viewById('perspective').elevation + 15);
  });
  it('has six named views and falls back to the 3D view', () => {
    expect(VIEWS.map((v) => v.id)).toEqual(['perspective', 'top', 'front', 'right', 'back', 'left']);
    expect(viewById('nope').id).toBe('perspective');
    expect(viewById('top').elevation).toBeGreaterThan(80);
  });
});

describe('fitDistance and orthoHeight', () => {
  it('backs further off for a bigger model and for a narrow window', () => {
    expect(fitDistance(10, 45, 1.6)).toBeGreaterThan(fitDistance(5, 45, 1.6));
    expect(fitDistance(10, 45, 0.5)).toBeGreaterThan(fitDistance(10, 45, 1.6));
  });
  it('makes the orthographic view as tall as the perspective one at the target', () => {
    expect(orthoHeight(10, 90)).toBeCloseTo(20);
    expect(orthoHeight(20, 60)).toBeCloseTo(2 * 20 * Math.tan(Math.PI / 6));
  });
});

describe('ease', () => {
  it('runs from 0 to 1 and is clamped', () => {
    expect(ease(0)).toBe(0); expect(ease(1)).toBe(1); expect(ease(-3)).toBe(0); expect(ease(9)).toBe(1); expect(ease(0.5)).toBeCloseTo(0.5);
  });
});

describe('isShown', () => {
  it('hides a category that is switched off', () => {
    const without = new Set(all); without.delete('roof');
    expect(isShown({ cat: 'roof', lv: 1 }, { upTo: null, categories: without })).toBe(false);
    expect(isShown({ cat: 'wall', lv: 1 }, { upTo: null, categories: without })).toBe(true);
  });
  it('shows the levels up to the chosen one, and things on no level always', () => {
    const s = { upTo: 0, categories: all };
    expect(isShown({ cat: 'wall', lv: 0 }, s)).toBe(true);
    expect(isShown({ cat: 'wall', lv: 1 }, s)).toBe(false);
    expect(isShown({ cat: 'wall', lv: -1 }, s)).toBe(true);
    expect(roomShown({ lv: 1 }, s)).toBe(false);
    expect(roomShown({ lv: 0 }, { upTo: null, categories: all })).toBe(true);
  });
  it('never hides what has no toggle', () => {
    expect(isShown({ cat: 'other', lv: 0 }, { upTo: null, categories: new Set() })).toBe(true);
  });
});

describe('subtitle', () => {
  it('says version, date and size', () => {
    expect(subtitle(3, '2026-10-26T09:24:11Z', 115)).toBe('Version 3 · 26 Oct 2026 · 115 elements');
    expect(subtitle(1, 'not a date', 5)).toBe('Version 1 · 5 elements');
  });
});

describe('base64 arrays', () => {
  it('reads floats and unsigned integers', () => {
    const f = new Float32Array([1.5, -2, 0.25]);
    const b = btoa(String.fromCharCode(...new Uint8Array(f.buffer)));
    expect(Array.from(floats(b))).toEqual([1.5, -2, 0.25]);
    const u = new Uint32Array([0, 7, 4000000000]);
    expect(Array.from(uints(btoa(String.fromCharCode(...new Uint8Array(u.buffer)))))).toEqual([0, 7, 4000000000]);
    expect(Array.from(fromBase64('AQID\n'))).toEqual([1, 2, 3]);
  });
});
