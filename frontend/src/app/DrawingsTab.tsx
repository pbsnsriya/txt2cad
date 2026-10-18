import { useState } from 'react';
import { Download, Maximize2, ZoomIn, ZoomOut } from 'lucide-react';
import { Button, IconButton } from '../ui/Button';
import { EmptyState } from '../ui/Surface';

const ZOOMS = [0.5, 0.75, 1, 1.5, 2, 3];

/** The plans exactly as the DXF has them (rendered from the same document), one drawing per level, left to right. */
export function DrawingsTab({ url, onDownload }: { url: string | null; onDownload: (format: string) => void }) {
  const [zoom, setZoom] = useState(2);
  const [failed, setFailed] = useState(false);
  if (!url) return <EmptyState title="Build something to see its floor plans here." />;
  const i = ZOOMS.indexOf(zoom);
  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
        <h2 className="mr-auto text-sm font-medium">Floor plans <span className="font-normal text-muted">1:100, metres, every level</span></h2>
        <IconButton label="Zoom out" size="sm" variant="secondary" disabled={i <= 0} onClick={() => setZoom(ZOOMS[i - 1])}><ZoomOut className="size-4" aria-hidden /></IconButton>
        <span className="w-12 text-center text-xs tabular-nums text-muted" aria-live="polite">{Math.round(zoom * 50)}%</span>
        <IconButton label="Zoom in" size="sm" variant="secondary" disabled={i >= ZOOMS.length - 1} onClick={() => setZoom(ZOOMS[i + 1])}><ZoomIn className="size-4" aria-hidden /></IconButton>
        <IconButton label="Fit to width" size="sm" variant="secondary" onClick={() => setZoom(1)}><Maximize2 className="size-4" aria-hidden /></IconButton>
        <Button size="sm" icon={<Download className="size-3.5" aria-hidden />} onClick={() => onDownload('dxf')}>DXF</Button>
        <Button size="sm" icon={<Download className="size-3.5" aria-hidden />} onClick={() => onDownload('svg')}>SVG</Button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto bg-surface p-4">
        {failed ? (
          <p role="alert" className="text-sm text-danger">The plans could not be drawn for this version.</p>
        ) : (
          <img src={url} alt="Floor plans of every level, drawn at 1:100" onError={() => setFailed(true)} style={{ width: `${zoom * 50}%`, minWidth: '20rem' }} className="max-w-none bg-white" />
        )}
      </div>
    </div>
  );
}
