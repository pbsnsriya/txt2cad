import { useEffect, useRef, useState } from 'react';
import { Box, BoxSelect, Info, Loader2, MousePointerClick, Scissors } from 'lucide-react';
import { IfcViewer, type Picked, type ViewName } from '../viewer/IfcViewer';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { CheckboxField, SliderField } from '../ui/Inputs';
import { Card, EmptyState } from '../ui/Surface';

const VIEWS: { id: ViewName; label: string }[] = [
  { id: 'iso', label: 'Corner' }, { id: 'top', label: 'Above' }, { id: 'front', label: 'Front' },
  { id: 'back', label: 'Back' }, { id: 'left', label: 'Left' }, { id: 'right', label: 'Right' },
];

export type OnReady = (h: ViewerHandle | null) => void;
export interface ViewerHandle { load: (url: string, refit?: boolean) => Promise<void>; clear: () => void; applyTheme: () => void; clearSelection: () => void; removeFromSelection: (guid: string) => void; highlight: (guids: string[]) => Promise<number> }

/** The 3D canvas plus its overlays. The parent drives it through `onReady` (a handle) so React never re-renders the canvas. */
export function ViewerPane({ badge, empty, building, theme, onReady, follow, onFollow, selected, onPick }: {
  badge: string; empty: boolean; building: boolean; theme: string; onReady: OnReady; follow: boolean; onFollow: (v: boolean) => void;
  selected: Picked[]; onPick: (p: Picked[]) => void;
}) {
  const [area, setArea] = useState(false);
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
      removeFromSelection: (guid) => void v.deselect(guid),
      highlight: (guids) => v.highlightGuids(guids),
    });
    return () => { onReady(null); v.dispose(); viewer.current = null; };
    // onReady is stable by contract (the parent stores the handle); the viewer is created once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { viewer.current?.applyTheme(); }, [theme]);
  useEffect(() => { viewer.current?.setAreaMode(area); }, [area]);
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
      <div role="toolbar" aria-label="Camera views" className="absolute left-1/2 top-12 flex max-w-[calc(100%-1.5rem)] -translate-x-1/2 gap-0.5 overflow-x-auto rounded-pill border border-border bg-surface p-1 shadow-card md:top-3">
        {VIEWS.map((v) => (
          <Button key={v.id} size="sm" variant="ghost" className="rounded-pill px-3" onClick={() => viewer.current?.setView(v.id)}>{v.label}</Button>
        ))}
        <span className="mx-1 w-px self-stretch bg-border" aria-hidden />
        <Button size="sm" variant={area ? 'primary' : 'ghost'} className="rounded-pill px-3" aria-pressed={area} icon={<BoxSelect className="size-4" aria-hidden />} onClick={() => setArea(!area)}>
          Select area
        </Button>
      </div>
      <Card variant="raised" className="absolute bottom-[4.5rem] left-3 hidden max-w-xs items-start gap-2 p-3 text-sm md:flex">
        {selected.length > 0 ? (
          <div className="flex min-w-0 flex-1 flex-col gap-1" data-testid="selection">
            <span className="flex items-center gap-1 text-xs font-medium text-muted"><MousePointerClick className="size-3.5" aria-hidden />{selected.length === 1 ? 'Selected' : `${selected.length} selected`}</span>
            <span className="truncate font-medium" title={selected.map((s) => s.name).join(', ')}>{selected[0].name || 'Unnamed element'}{selected.length > 1 ? ` and ${selected.length - 1} more` : ''}</span>
            <span className="text-xs text-muted">{selected.length === 1 ? `${selected[0].category.replace(/^Ifc/, '') || 'Element'}. Your next message is about it.` : 'Your next message is about all of them.'} Shift-click adds or removes one.</span>
            <Button size="sm" variant="ghost" className="self-start" onClick={() => viewer.current?.clearSelection()}>{selected.length === 1 ? 'Unpick' : 'Unpick all'}</Button>
          </div>
        ) : (
          <>
            <Info className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
            <span className="pointer-events-none text-muted">{area ? 'Drag a box over the part you want. Hold Shift to add to what is already picked.' : 'Click any part of the building to pick it, Shift-click to pick more, or use Select area. Drag to turn it, scroll to zoom.'}</span>
          </>
        )}
      </Card>
      <Card variant="raised" className="absolute bottom-3 left-3 right-3 flex items-center gap-3 p-2">
        <Scissors className="ml-1 size-4 shrink-0 text-muted" aria-hidden />
        <div className="w-full max-w-md">
          <SliderField label="Cut height" value={section} min={0.05} max={1} step={0.01} onChange={setSection}
            valueText={section >= 0.999 ? 'full height' : `cut at ${cutMetres.toFixed(1)} m`} />
        </div>
        <span className="w-28 shrink-0 text-xs text-muted tabular-nums">{section >= 0.999 ? 'full height' : `cut at ${cutMetres.toFixed(1)} m`}</span>
        <CheckboxField label="Keep in view" checked={follow} onCheckedChange={onFollow} />
      </Card>
    </div>
  );
}
