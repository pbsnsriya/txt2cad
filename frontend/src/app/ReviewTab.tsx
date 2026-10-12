import { CheckCircle2, CircleSlash, Eye, XCircle } from 'lucide-react';
import type { Analysis, Clause } from '../api/client';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card, EmptyState, Skeleton } from '../ui/Surface';

const ICON = {
  pass: <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />,
  fail: <XCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />,
  info: <CircleSlash className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />,
};

function ClauseRow({ c, onShow }: { c: Clause; onShow: (guids: string[]) => void }) {
  return (
    <li className="flex gap-3 border-t border-border py-3 first:border-t-0">
      {ICON[c.status]}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium"><span className="sr-only">{c.status}: </span>{c.title}</span>
          <Badge mono>{c.section}</Badge>
        </div>
        <p className="mt-0.5 text-sm text-muted">Measured: {c.measured}{c.required !== '-' && <> &nbsp;|&nbsp; Needed: {c.required}</>}</p>
        {c.status === 'fail' && c.fix && <p className="mt-1 text-sm text-danger">{c.fix}</p>}
      </div>
      {c.guids.length > 0 && <Button size="sm" variant="ghost" icon={<Eye className="size-3.5" aria-hidden />} onClick={() => onShow(c.guids)}>Show in model</Button>}
    </li>
  );
}

/** An indicative check against a few dwelling rules. It says so, loudly, because it is not a compliance report. */
export function ReviewTab({ analysis, loading, onShow }: { analysis: Analysis | null; loading: boolean; onShow: (guids: string[]) => void }) {
  if (loading) return <div className="flex flex-col gap-3 p-4"><Skeleton className="h-20" /><Skeleton className="h-40" /></div>;
  if (!analysis) return <EmptyState title="Build something to check it here." />;
  const r = analysis.review;
  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        <div>
          <h2 className="text-lg font-semibold">Design check</h2>
          <p className="text-sm text-muted">{r.ruleset}</p>
          <p role="note" className="mt-2 rounded-md bg-warning-soft px-3 py-2 text-sm text-warning">{r.disclaimer}</p>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[['Floor area', `${r.summary.gross_area_m2} m2`], ['Levels', r.summary.levels], ['Passing', r.summary.pass], ['Failing', r.summary.fail]].map(([k, v]) => (
            <Card key={String(k)} className="p-3"><div className="text-xs text-muted">{k}</div><div className="text-xl font-semibold tabular-nums">{v}</div></Card>
          ))}
        </div>
        <Card className="p-0 px-4"><ul aria-label="Checks">{r.clauses.map((c) => <ClauseRow key={c.id} c={c} onShow={onShow} />)}</ul></Card>
      </div>
    </div>
  );
}
