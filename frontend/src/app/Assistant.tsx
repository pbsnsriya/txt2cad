import { useEffect, useRef } from 'react';
import { CheckCircle2, CircleSlash, Download, RotateCcw, XCircle } from 'lucide-react';
import type { ProjectDetail } from '../api/client';
import type { RunView } from '../state/run';
import { TraceSection } from '../ui/Trace';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card, ListRow } from '../ui/Surface';

const PHASE_ORDER = ['Setup', 'Rooms', 'Doors and stairs', 'Windows and roof', 'Changes', 'Notes', 'Other'];

export function Trace({ run }: { run: RunView }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { if (run.status === 'running') end.current?.scrollIntoView({ block: 'end' }); }, [run.phases, run.draft, run.status]);
  if (run.status === 'idle') return null;
  const phases = [...run.phases].sort((a, b) => PHASE_ORDER.indexOf(a.name) - PHASE_ORDER.indexOf(b.name));
  const lastIndex = phases.length - 1;
  return (
    <div className="flex flex-col gap-4" aria-label="Run trace">
      <Card variant="sunken" className="text-sm"><span className="font-medium">Your request:</span> {run.prompt}</Card>
      <TraceSection title="Understanding the request" state={run.checklist.length || run.status !== 'running' ? 'done' : 'active'}
        rationale={run.approach || undefined} stepsLabel="requirement" steps={run.checklist.map((c) => c.text + (c.supported ? '' : ' (not supported yet)'))} />
      {phases.map((p, i) => (
        <TraceSection key={p.name} title={p.name} state={p.errors.length && !p.steps.length ? 'rejected' : run.status === 'running' && i === lastIndex ? 'active' : 'done'}
          liveLine={run.draft || undefined} steps={p.steps.map((s) => s.text)} error={p.errors.join('\n') || undefined}
          rationale={p.steps.find((s) => s.why)?.why} />
      ))}
      {run.verify.length > 0 && <Checklist run={run} />}
      {run.status === 'error' && <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{run.error}</p>}
      {run.status === 'done' && <p className="text-sm text-muted">{run.summary}</p>}
      {run.notes.length > 0 && <ul className="list-disc pl-5 text-sm text-muted">{run.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      <div ref={end} />
    </div>
  );
}

function Checklist({ run }: { run: RunView }) {
  return (
    <section className="flex flex-col gap-1">
      <h3 className="text-sm font-medium">Compared with your request: {run.verifyText}</h3>
      <ul className="flex flex-col gap-1 text-sm">
        {run.verify.map((r, i) => (
          <li key={i} className="flex items-start gap-2">
            {r.status === 'met' ? <CheckCircle2 className="mt-0.5 size-4 text-success" aria-hidden /> : r.status === 'unmet' ? <XCircle className="mt-0.5 size-4 text-danger" aria-hidden /> : <CircleSlash className="mt-0.5 size-4 text-muted" aria-hidden />}
            <span><span className="sr-only">{r.status}: </span>{r.text} <span className="text-muted">{r.detail && `(${r.detail})`}</span></span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** "Layout option 2 (Open plan): the living area faces south." out of a version summary, when it has one. */
function layoutNote(summary: string): string | null {
  const m = summary.match(/Layout option \d \([^)]+\): .*$/);
  return m ? m[0] : null;
}

export function VersionList({ detail, viewing, onOpen, onRestore, onDownload, busy }: {
  detail: ProjectDetail; viewing: number; onOpen: (n: number) => void; onRestore: (n: number) => void; onDownload: (n: number, f: string) => void; busy: boolean;
}) {
  const versions = [...detail.versions].reverse();
  return (
    <section className="flex flex-col gap-2" aria-label="Version history">
      <h3 className="text-sm font-medium">History</h3>
      {versions.map((v) => (
        <Card key={v.number} variant="flat" selected={v.number === viewing} className="flex flex-col gap-2 p-3">
          <div className="flex items-center justify-between gap-2">
            <Badge tone={v.number === detail.versions.length ? 'info' : 'neutral'}>v{v.number}{v.mode === 'revert' ? ' restored' : ''}</Badge>
            <div className="flex gap-1">
              <Button size="sm" variant="ghost" onClick={() => onOpen(v.number)} disabled={v.number === viewing}>Open</Button>
              <Button size="sm" variant="ghost" icon={<Download className="size-3.5" aria-hidden />} onClick={() => onDownload(v.number, 'ifc')}>IFC</Button>
              <Button size="sm" variant="ghost" icon={<Download className="size-3.5" aria-hidden />} onClick={() => onDownload(v.number, 'dxf')}>DXF</Button>
              {v.number !== detail.versions.length && (
                <Button size="sm" variant="ghost" icon={<RotateCcw className="size-3.5" aria-hidden />} disabled={busy} onClick={() => onRestore(v.number)}>Restore</Button>
              )}
            </div>
          </div>
          <p className="line-clamp-2 text-sm text-muted" title={v.prompt}>{v.prompt}</p>
          {layoutNote(v.summary) && <p className="text-xs text-fg">{layoutNote(v.summary)}</p>}
        </Card>
      ))}
    </section>
  );
}

export function SessionRow({ title, selected, onClick }: { title: string; selected: boolean; onClick: () => void }) {
  return <ListRow title={title} selected={selected} onClick={onClick} />;
}
