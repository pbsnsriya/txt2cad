import { useState } from 'react';
import { Check, ChevronRight, Loader2, XCircle } from 'lucide-react';
import { cn, focusRing } from './cn';

export type TraceState = 'pending' | 'active' | 'done' | 'rejected';

export interface TraceSectionProps {
  title: string;
  state: TraceState;
  rationale?: string;
  liveLine?: string;      // the step being written right now ("Cutting a window in the kitchen")
  error?: string;         // model-readable rejection message
  steps?: string[];       // one sentence per applied step
  stepsLabel?: string;    // noun for the collapsed list: "step" by default
}

/** One phase of a run. Steps are collapsed by default; the live line is announced politely. */
export function TraceSection({ title, state, rationale, liveLine, error, steps = [], stepsLabel = 'step' }: TraceSectionProps) {
  const [open, setOpen] = useState(false);
  const icon =
    state === 'active' ? <Loader2 className="size-4 animate-spin text-accent" aria-hidden />
    : state === 'done' ? <Check className="size-4 text-success" aria-hidden />
    : state === 'rejected' ? <XCircle className="size-4 text-danger" aria-hidden />
    : <span className="size-4 rounded-pill border border-border" aria-hidden />;
  return (
    <section className="flex flex-col gap-1">
      <div className="flex items-center gap-2 text-sm font-medium">
        {icon}
        <span>{title}</span>
        <span className="sr-only">{state}</span>
      </div>
      {rationale && <p className="ml-6 text-sm italic text-muted">{rationale}</p>}
      {state === 'active' && liveLine && <p className="ml-6 text-sm text-fg" aria-live="polite">{liveLine}...</p>}
      {state === 'rejected' && error && (
        <p role="alert" className="ml-6 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>
      )}
      {steps.length > 0 && (
        <div className="ml-6">
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
            className={cn('inline-flex items-center gap-1 rounded-md py-1 text-xs text-muted hover:text-fg', focusRing)}
          >
            <ChevronRight className={cn('size-3.5 transition-transform duration-fast', open && 'rotate-90')} aria-hidden />
            {steps.length} {stepsLabel}{steps.length === 1 ? '' : 's'}
          </button>
          {open && <ul className="mt-1 list-disc pl-5 text-sm text-muted">{steps.map((s) => <li key={s}>{s}</li>)}</ul>}
        </div>
      )}
    </section>
  );
}
