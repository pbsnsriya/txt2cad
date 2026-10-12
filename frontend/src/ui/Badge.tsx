import type { ReactNode } from 'react';
import { cn } from './cn';

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

const tones: Record<Tone, string> = {
  neutral: 'bg-surface-sunken text-fg',
  info: 'bg-accent-soft text-accent-text',
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
};

/** Status text always travels with the colour; never use a Badge with colour only. */
export function Badge({ tone = 'neutral', mono, icon, children }: { tone?: Tone; mono?: boolean; icon?: ReactNode; children: ReactNode }) {
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-xs font-medium', mono && 'font-mono', tones[tone])}>
      {icon}
      {children}
    </span>
  );
}

export function Chip({ selected, children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { selected?: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      {...rest}
      className={cn(
        'h-11 rounded-pill border px-4 text-sm transition-colors duration-fast disabled:opacity-50',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent outline-none',
        selected ? 'border-accent bg-accent-soft text-accent-text' : 'border-border bg-surface text-fg hover:bg-surface-sunken',
      )}
    >
      {children}
    </button>
  );
}
