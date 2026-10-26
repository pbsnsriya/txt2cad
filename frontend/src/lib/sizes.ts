/** Helpers for the Sizes tab: reading what is there, and what a person typed. */

export interface RoomRow { id: string; name: string; level: string; rect: number[] }

export const MIN_SIDE = 1.5;
export const MAX_SIDE = 40;

/** The number in a text box, or null when it is empty or not a number. A comma is accepted as the decimal mark. */
export function parseMetres(text: string): number | null {
  const t = text.trim().replace(',', '.');
  if (!t || !/^\d*\.?\d+$|^\d+\.$/.test(t)) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/** A problem with a typed size, in words, or '' when it is fine (or empty: nothing typed means no change). */
export function sizeProblem(text: string, label: string): string {
  if (!text.trim()) return '';
  const n = parseMetres(text);
  if (n === null) return `${label} must be a number of metres`;
  if (n < MIN_SIDE || n > MAX_SIDE) return `${label} must be between ${MIN_SIDE} and ${MAX_SIDE} m`;
  return '';
}

export function show(n: number): string {
  return String(Math.round(n * 100) / 100);
}

/** Width and depth of the ground floor outline, as the check measures it: the lowest level that has rooms. */
export function footprint(levels: { id: string }[], rooms: RoomRow[]): { width: number; depth: number } | null {
  for (const lv of levels) {
    const here = rooms.filter((r) => r.level === lv.id);
    if (!here.length) continue;
    const x0 = Math.min(...here.map((r) => r.rect[0])), x1 = Math.max(...here.map((r) => r.rect[0] + r.rect[2]));
    const y0 = Math.min(...here.map((r) => r.rect[1])), y1 = Math.max(...here.map((r) => r.rect[1] + r.rect[3]));
    return { width: Math.round((x1 - x0) * 100) / 100, depth: Math.round((y1 - y0) * 100) / 100 };
  }
  return null;
}

export interface Typed { width: string; depth: string }

/** What to send for the rooms: only the sizes that differ from what is there now. */
export function roomChanges(rooms: RoomRow[], typed: Record<string, Typed>): { room: string; width?: number; depth?: number }[] {
  const out: { room: string; width?: number; depth?: number }[] = [];
  for (const r of rooms) {
    const t = typed[r.id];
    if (!t) continue;
    const w = parseMetres(t.width), d = parseMetres(t.depth);
    const change: { room: string; width?: number; depth?: number } = { room: r.id };
    if (w !== null && Math.abs(w - r.rect[2]) > 1e-6) change.width = w;
    if (d !== null && Math.abs(d - r.rect[3]) > 1e-6) change.depth = d;
    if (change.width !== undefined || change.depth !== undefined) out.push(change);
  }
  return out;
}
