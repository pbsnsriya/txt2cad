import type { HTMLAttributes, ReactNode } from 'react';
import { Loader2, Inbox } from 'lucide-react';
import { cn, focusRing } from './cn';

export function Card({ variant = 'flat', selected, className, ...rest }: HTMLAttributes<HTMLDivElement> & { variant?: 'flat' | 'raised' | 'sunken'; selected?: boolean }) {
  return (
    <div
      {...rest}
      className={cn(
        'rounded-lg p-4 border',
        variant === 'sunken' ? 'bg-surface-sunken border-transparent' : 'bg-surface',
        variant === 'raised' && 'shadow-card',
        selected ? 'border-accent' : variant !== 'sunken' && 'border-border',
        className,
      )}
    />
  );
}

/** Row used for sessions, recorded runs and review clauses. Title truncates; the full text stays in the title attribute. */
export function ListRow({ icon, title, meta, selected, onClick }: { icon?: ReactNode; title: string; meta?: ReactNode; selected?: boolean; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={selected || undefined}
      className={cn(
        'flex w-full items-center gap-3 rounded-md border px-3 h-10 text-left text-sm transition-colors duration-fast', focusRing,
        selected ? 'bg-accent-soft border-transparent text-fg' : 'bg-surface border-border hover:bg-surface-sunken',
      )}
    >
      {icon && <span className="text-accent shrink-0" aria-hidden>{icon}</span>}
      <span className="min-w-0 flex-1 truncate" title={title}>{title}</span>
      {meta && <span className="shrink-0 text-xs text-muted">{meta}</span>}
    </button>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label ?? <span className="sr-only">Loading</span>}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('rounded-md bg-border motion-safe:animate-pulse', className)} />;
}

export function EmptyState({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center text-sm text-muted">
      <Inbox className="size-6" aria-hidden />
      <p>{title}</p>
      {action}
    </div>
  );
}

export function Table({ caption, head, rows }: { caption: string; head: string[]; rows: Array<Array<string | number>> }) {
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>{head.map((h, i) => <th key={h} scope="col" className={cn('px-3 py-2 text-xs font-medium text-muted', (i > 0 ? 'text-right' : 'text-left'))}>{h}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-t border-border hover:bg-surface-sunken">
            {r.map((c, j) => <td key={j} className={cn('px-3 py-2', j > 0 && 'text-right tabular-nums')}>{c}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
