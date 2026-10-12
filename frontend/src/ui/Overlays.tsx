import { useCallback, useRef, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Info, CheckCircle2, AlertTriangle, XCircle, X } from 'lucide-react';
import { cn, focusRing } from './cn';
import { Button } from './Button';
import type { Tone } from './Badge';

/** Confirm dialog. Initial focus lands on Cancel, the safe action; the danger button names the object. */
export function ConfirmDialog({ open, onOpenChange, title, body, confirmLabel, busy, onConfirm }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; body: string; confirmLabel: string; busy?: boolean; onConfirm: () => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-fg/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,26rem)] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-surface p-5 shadow-pop">
          <Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-muted">{body}</Dialog.Description>
          <div className="mt-5 flex justify-end gap-2">
            <Dialog.Close asChild><Button variant="secondary" autoFocus>Cancel</Button></Dialog.Close>
            <Button variant="danger" loading={busy} onClick={onConfirm}>{confirmLabel}</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

const toastIcon: Record<Exclude<Tone, 'neutral'>, ReactNode> = {
  info: <Info className="size-4" aria-hidden />,
  success: <CheckCircle2 className="size-4" aria-hidden />,
  warning: <AlertTriangle className="size-4" aria-hidden />,
  danger: <XCircle className="size-4" aria-hidden />,
};
const toastTone: Record<Exclude<Tone, 'neutral'>, string> = {
  info: 'bg-accent-soft text-accent-text', success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning', danger: 'bg-danger-soft text-danger',
};

/** Presentational toast. danger uses role="alert"; others role="status". Auto-dismiss is the host's job. */
export function Toast({ tone, children, onDismiss }: { tone: Exclude<Tone, 'neutral'>; children: ReactNode; onDismiss: () => void }) {
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} className={cn('flex items-start gap-2 rounded-md px-3 py-2 text-sm shadow-card', toastTone[tone])}>
      <span className="mt-0.5">{toastIcon[tone]}</span>
      <div className="flex-1">{children}</div>
      <button type="button" aria-label="Dismiss" onClick={onDismiss} className={cn('rounded-sm p-0.5 hover:bg-fg/10', focusRing)}>
        <X className="size-4" aria-hidden />
      </button>
    </div>
  );
}

/** Drag handle for a panel edge. Arrow keys nudge 8px (Shift 32px); double-click resets. */
export function Resizer({ label, value, min, max, onChange, onReset, side = 'left' }: {
  label: string; value: number; min: number; max: number; onChange: (v: number) => void; onReset: () => void; side?: 'left' | 'right';
}) {
  const start = useRef<{ x: number; v: number } | null>(null);
  const clamp = useCallback((v: number) => Math.min(max, Math.max(min, v)), [min, max]);
  const sign = side === 'left' ? -1 : 1; // dragging a left-edge handle to the left grows the panel
  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => { e.currentTarget.setPointerCapture(e.pointerId); start.current = { x: e.clientX, v: value }; };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => { if (start.current) onChange(clamp(start.current.v + sign * (e.clientX - start.current.x))); };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 32 : 8;
    // Moving the handle left (ArrowLeft) is a negative dx, same as a leftward drag.
    if (e.key === 'ArrowLeft') onChange(clamp(value + sign * -step));
    if (e.key === 'ArrowRight') onChange(clamp(value + sign * step));
  };
  return (
    <div
      role="separator" aria-orientation="vertical" aria-label={label}
      aria-valuenow={value} aria-valuemin={min} aria-valuemax={max} tabIndex={0}
      onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={() => (start.current = null)}
      onDoubleClick={onReset} onKeyDown={onKey}
      className={cn('w-1.5 cursor-col-resize bg-transparent hover:bg-accent/40 focus-visible:bg-accent/60', focusRing)}
    />
  );
}
