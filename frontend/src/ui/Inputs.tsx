import { useId, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react';
import * as Checkbox from '@radix-ui/react-checkbox';
import * as Slider from '@radix-ui/react-slider';
import { AlertCircle, Check } from 'lucide-react';
import { cn, focusRing } from './cn';

const field = 'w-full rounded-md border bg-surface px-3 text-sm text-fg placeholder:text-muted disabled:opacity-50 disabled:cursor-not-allowed read-only:bg-surface-sunken';

/** Label is always present (use hideLabel for a visually hidden one). Error is linked with aria-describedby. */
export function Input({ label, hideLabel, error, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: string; hideLabel?: boolean; error?: string }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className={cn('text-sm font-medium', hideLabel && 'sr-only')}>{label}</label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-err` : undefined}
        {...rest}
        className={cn(field, 'h-10', error ? 'border-danger' : 'border-input', focusRing, className)}
      />
      {error && (
        <p id={`${id}-err`} className="flex items-center gap-1 text-xs text-danger">
          <AlertCircle className="size-3.5" aria-hidden />
          {error}
        </p>
      )}
    </div>
  );
}

export function Textarea({ label, error, className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; error?: string }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="sr-only">{label}</label>
      <textarea id={id} aria-invalid={error ? true : undefined} {...rest} className={cn(field, 'py-2', error ? 'border-danger' : 'border-input', focusRing, className)} />
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}

export function CheckboxField({ label, checked, onCheckedChange, disabled }: { label: string; checked: boolean; onCheckedChange: (v: boolean) => void; disabled?: boolean }) {
  const id = useId();
  return (
    <div className="flex items-center gap-2">
      <Checkbox.Root
        id={id}
        checked={checked}
        disabled={disabled}
        onCheckedChange={(v) => onCheckedChange(v === true)}
        className={cn('grid size-5 place-items-center rounded-sm border border-input bg-surface data-[state=checked]:bg-accent data-[state=checked]:border-accent disabled:opacity-50', focusRing)}
      >
        <Checkbox.Indicator><Check className="size-3.5 text-on-accent" aria-hidden /></Checkbox.Indicator>
      </Checkbox.Root>
      <label htmlFor={id} className="text-sm">{label}</label>
    </div>
  );
}

/** Section-cut style slider. valueText feeds aria-valuetext ("cut at 5.7 m"). */
export function SliderField({ label, value, min, max, step = 0.1, onChange, valueText }: {
  label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void; valueText: string;
}) {
  return (
    <Slider.Root
      value={[value]} min={min} max={max} step={step}
      onValueChange={(v) => onChange(v[0] ?? value)}
      className="relative flex h-5 w-full touch-none select-none items-center"
    >
      <Slider.Track className="relative h-1.5 grow rounded-pill bg-border">
        <Slider.Range className="absolute h-full rounded-pill bg-accent" />
      </Slider.Track>
      <Slider.Thumb aria-label={label} aria-valuetext={valueText} className={cn('block size-4 rounded-pill border-2 border-accent bg-surface', focusRing)} />
    </Slider.Root>
  );
}
