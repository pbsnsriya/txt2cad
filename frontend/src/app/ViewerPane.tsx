import { useEffect, useRef, useState } from 'react';
import { Box, Info, Loader2, MousePointerClick, Scissors } from 'lucide-react';
import { IfcViewer, type Picked, type ViewName } from '../viewer/IfcViewer';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { CheckboxField, SliderField } from '../ui/Inputs';
import { Card, EmptyState } from '../ui/Surface';

const VIEWS: { id: ViewName; label: string }[] = [
  { id: 'top', label: 'Top' }, { id: 'bottom', label: 'Bottom' }, { id: 'front', label: 'Front' }, { id: 'back', label: 'Back' },
  { id: 'left', label: 'Left' }, { id: 'right', label: 'Right' }, { id: 'iso', label: 'Isometric' },
];

export type OnReady = (h: ViewerHandle | null) => void;
export interface ViewerHandle { load: (url: string, refit?: boolean) => Promise<void>; clear: () => void; applyTheme: () => void; clearSelection: () => void; highlight: (guids: string[]) => Promise<number> }

/** The 3D canvas plus its overlays. The parent drives it through `onReady` (a handle) so React never re-renders the canvas. */
export function ViewerPane({ badge, empty, building, theme, onReady, follow, onFollow, selected, onPick }: {
  badge: string; empty: boolean; building: boolean; theme: string; onReady: OnReady; follow: boolean; onFollow: (v: boolean) => void;
  selected: Picked | null; onPick: (p: Picked | null) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const viewer = useRef<IfcViewer | null>(null);
  const [section, setSection] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const v = new IfcViewer(host.current!);
    v.onPick = onPick;
    viewer.current = v;
    onReady({
      load: async (url, refit) => {
        setLoading(true);
        try { if (await v.load(url, 'model', refit)) host.current?.setAttribute('data-model-url', url); setError(''); } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
      },
      clear: () => v.clear(),
      applyTheme: () => v.applyTheme(),
      clearSelection: () => v.clearSelection(),
      highlight: (guids) => v.highlightGuids(guids),
    });
    return () => { onReady(null); v.dispose(); viewer.current = null; };
    // onReady is stable by contract (the parent stores the handle); the viewer is created once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { viewer.current?.applyTheme(); }, [theme]);
  useEffect(() => { viewer.current?.setSection(section); }, [section]);

  const cutMetres = (section * (viewer.current?.height() ?? 0));
  return (
    <div className="relative h-full min-h-0 w-full overflow-hidden bg-viewer-bg" data-testid="viewer">
      <div ref={host} className="absolute inset-0" aria-label="3D model viewer" role="img" />
      {empty && !building && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <EmptyState title="Describe a building to see it here." />
        </div>
      )}
      <div className="absolute left-3 top-3 flex items-center gap-2">
        {badge && <Badge tone={building ? 'warning' : 'info'} mono icon={building ? <Loader2 className="size-3 animate-spin" aria-hidden /> : <Box className="size-3" aria-hidden />}>{badge}</Badge>}
        {loading && !building && <Badge>Loading model...</Badge>}
        {error && <Badge tone="danger">{error}</Badge>}
      </div>
      <Card variant="raised" className="absolute right-3 top-3 flex w-36 flex-col gap-1 p-1 md:w-44 md:p-2" role="toolbar" aria-label="Camera views">
        <div className="grid grid-cols-2 gap-1">
          {VIEWS.map((v) => (
            <Button key={v.id} size="sm" variant="ghost" className={v.id === 'iso' ? 'col-span-2' : ''} onClick={() => viewer.current?.setView(v.id)}>{v.label}</Button>
          ))}
        </div>
      </Card>
      <Card variant="raised" className="absolute bottom-[4.5rem] left-3 hidden max-w-xs items-start gap-2 p-3 text-sm md:flex">
        {selected ? (
          <div className="flex min-w-0 flex-1 flex-col gap-1" data-testid="selection">
            <span className="flex items-center gap-1 text-xs font-medium text-muted"><MousePointerClick className="size-3.5" aria-hidden />Selected</span>
            <span className="truncate font-medium" title={selected.name}>{selected.name || 'Unnamed element'}</span>
            <span className="text-xs text-muted">{selected.category.replace(/^Ifc/, '') || 'Element'}. Your next message is about this.</span>
            <Button size="sm" variant="ghost" className="self-start" onClick={() => viewer.current?.clearSelection()}>Clear selection</Button>
          </div>
        ) : (
          <>
            <Info className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
            <span className="pointer-events-none text-muted">Click an element to select it, then describe the change. Drag to orbit, scroll to zoom.</span>
          </>
        )}
      </Card>
      <Card variant="raised" className="absolute bottom-3 left-3 right-3 flex items-center gap-3 p-2">
        <Scissors className="ml-1 size-4 shrink-0 text-muted" aria-hidden />
        <div className="w-full max-w-md">
          <SliderField label="Section height" value={section} min={0.05} max={1} step={0.01} onChange={setSection}
            valueText={section >= 0.999 ? 'full height' : `cut at ${cutMetres.toFixed(1)} m`} />
        </div>
        <span className="w-28 shrink-0 text-xs text-muted tabular-nums">{section >= 0.999 ? 'full height' : `cut at ${cutMetres.toFixed(1)} m`}</span>
        <CheckboxField label="Follow build" checked={follow} onCheckedChange={onFollow} />
      </Card>
    </div>
  );
}
