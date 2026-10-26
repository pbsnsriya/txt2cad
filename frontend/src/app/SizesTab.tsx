import { useEffect, useMemo, useState } from 'react';
import type { VersionInfo } from '../api/client';
import { footprint, roomChanges, show, sizeProblem, type Typed } from '../lib/sizes';
import { Button } from '../ui/Button';
import { Card, EmptyState } from '../ui/Surface';

export type SizeChange = { rooms: { room: string; width?: number; depth?: number }[] } | { building_width?: number; building_depth?: number };

const field = 'h-8 w-20 rounded-md border border-input bg-surface px-2 text-right tabular-nums';

/** Sizes by hand: type a new width or depth and the plan is stretched to fit. No model is called, so it is instant and costs nothing. */
export function SizesTab({ head, busy, onApply }: { head: VersionInfo | null; busy: boolean; onApply: (change: SizeChange) => Promise<string | null> }) {
  const rooms = head?.design.rooms ?? [];
  const levels = head?.design.levels ?? [];
  const outline = useMemo(() => footprint(levels, rooms), [levels, rooms]);
  const [typed, setTyped] = useState<Record<string, Typed>>({});
  const [bw, setBw] = useState('');
  const [bd, setBd] = useState('');
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { setTyped({}); setBw(''); setBd(''); }, [head?.number]);          // a new version: start from what it says

  if (!head || !rooms.length) return <EmptyState title="Build something to change its sizes here." />;

  const changes = roomChanges(rooms, typed);
  const problems = rooms.flatMap((r) => [sizeProblem(typed[r.id]?.width ?? '', `${r.name} width`), sizeProblem(typed[r.id]?.depth ?? '', `${r.name} depth`)]).filter(Boolean);
  const bProblems = [sizeProblem(bw, 'The building width'), sizeProblem(bd, 'The building depth')].filter(Boolean);
  const bw_ = Number(bw.replace(',', '.')), bd_ = Number(bd.replace(',', '.'));
  const buildingChange = (bw.trim() ? { building_width: bw_ } : {}) as { building_width?: number };
  const buildingChange2 = (bd.trim() ? { building_depth: bd_ } : {}) as { building_depth?: number };

  async function apply(change: SizeChange) {
    setMessage(null);
    const error = await onApply(change);
    setMessage(error ? { ok: false, text: error } : { ok: true, text: 'Saved as a new version. The 3D view and the plans show it.' });
  }
  const edit = (id: string, key: keyof Typed, value: string) => setTyped((t) => ({ ...t, [id]: { width: t[id]?.width ?? '', depth: t[id]?.depth ?? '', [key]: value.replace(/[^0-9.,]/g, '') } }));

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        <div>
          <h2 className="text-lg font-semibold">Sizes</h2>
          <p className="text-sm text-muted">
            Type a new width (east to west) or depth (north to south). The rooms beside it move over, doors and windows are put back, and the change is saved as a new version.
            No model is used, so it takes a moment and costs nothing.
          </p>
        </div>
        {message && <p data-testid="sizes-message" role={message.ok ? 'status' : 'alert'} className={message.ok ? 'text-sm text-success' : 'text-sm text-danger'}>{message.text}</p>}

        {outline && (
          <Card className="flex flex-col gap-2 p-3">
            <h3 className="text-sm font-medium">Whole building</h3>
            <p className="text-xs text-muted">The outline of the ground floor is {show(outline.width)} x {show(outline.depth)} m. Every room is stretched evenly.</p>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-xs">Width (m)
                <input aria-label="Building width in metres" inputMode="decimal" placeholder={show(outline.width)} value={bw} onChange={(e) => setBw(e.target.value.replace(/[^0-9.,]/g, ''))} className={field} />
              </label>
              <label className="flex flex-col gap-1 text-xs">Depth (m)
                <input aria-label="Building depth in metres" inputMode="decimal" placeholder={show(outline.depth)} value={bd} onChange={(e) => setBd(e.target.value.replace(/[^0-9.,]/g, ''))} className={field} />
              </label>
              <Button size="sm" variant="primary" loading={busy} disabled={busy || (!bw.trim() && !bd.trim()) || bProblems.length > 0}
                onClick={() => void apply({ ...buildingChange, ...buildingChange2 })}>Apply to the building</Button>
            </div>
            {bProblems.map((p) => <p key={p} role="alert" className="text-xs text-danger">{p}</p>)}
          </Card>
        )}

        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <caption className="sr-only">Room sizes</caption>
            <thead><tr className="text-xs text-muted">
              <th scope="col" className="px-3 py-2 text-left">Room</th><th scope="col" className="px-3 py-2 text-right">Width (m)</th>
              <th scope="col" className="px-3 py-2 text-right">Depth (m)</th><th scope="col" className="px-3 py-2 text-right">Area (m²)</th>
            </tr></thead>
            {levels.map((lv) => (
              <tbody key={lv.id}>
                {levels.length > 1 && <tr><th colSpan={4} scope="colgroup" className="bg-surface-sunken px-3 py-1 text-left text-xs font-medium text-muted">{lv.name || lv.id}</th></tr>}
                {rooms.filter((r) => r.level === lv.id).map((r) => {
                  const t = typed[r.id];
                  const w = t?.width ?? '', d = t?.depth ?? '';
                  const changed = changes.some((c) => c.room === r.id);
                  return (
                    <tr key={r.id} className={`border-t border-border ${changed ? 'bg-surface-sunken' : ''}`}>
                      <td className="px-3 py-2">{r.name}</td>
                      <td className="px-3 py-2 text-right">
                        <input aria-label={`${r.name} width in metres`} inputMode="decimal" placeholder={show(r.rect[2])} value={w} onChange={(e) => edit(r.id, 'width', e.target.value)} className={field} />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <input aria-label={`${r.name} depth in metres`} inputMode="decimal" placeholder={show(r.rect[3])} value={d} onChange={(e) => edit(r.id, 'depth', e.target.value)} className={field} />
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-muted">{show(r.rect[2] * r.rect[3])}</td>
                    </tr>
                  );
                })}
              </tbody>
            ))}
          </table>
        </Card>
        {problems.map((p) => <p key={p} role="alert" className="text-xs text-danger">{p}</p>)}
        <div className="sticky bottom-0 -mx-4 -mb-4 flex flex-wrap items-center gap-3 border-t border-border bg-surface px-4 py-3">
          <Button variant="primary" loading={busy} disabled={busy || changes.length === 0 || problems.length > 0} onClick={() => void apply({ rooms: changes })}>
            Apply {changes.length > 1 ? `${changes.length} changes` : 'the change'}
          </Button>
          <Button variant="ghost" disabled={busy || changes.length === 0} onClick={() => setTyped({})}>Clear</Button>
          <p className="text-xs text-muted">Version {head.number} is the starting point.</p>
        </div>
      </div>
    </div>
  );
}
