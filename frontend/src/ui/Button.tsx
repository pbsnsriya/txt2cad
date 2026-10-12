import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { cn, focusRing } from './cn';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

const variants: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-on-accent hover:brightness-95 active:brightness-90',
  secondary: 'bg-surface text-fg border border-border hover:bg-surface-sunken active:bg-surface-sunken',
  ghost: 'bg-transparent text-fg hover:bg-surface-sunken active:bg-surface-sunken',
  danger: 'bg-danger text-on-accent hover:brightness-95 active:brightness-90',
};
const sizes: Record<ButtonSize, string> = { sm: 'h-8 px-3 text-sm', md: 'h-10 px-4 text-sm' };

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
}

/** Real <button>. Loading keeps the label (screen readers) and sets aria-busy. */
export function Button({ variant = 'secondary', size = 'md', loading, icon, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors duration-fast',
        'disabled:opacity-50 disabled:cursor-not-allowed', focusRing, variants[variant], sizes[size], className,
      )}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'> {
  label: string; // required: icon-only buttons must have an accessible name
  variant?: 'ghost' | 'secondary' | 'accent';
  size?: ButtonSize;
  round?: boolean;
  children: ReactNode;
}

export function IconButton({ label, variant = 'ghost', size = 'md', round, className, children, ...rest }: IconButtonProps) {
  const v = {
    ghost: 'bg-transparent text-fg hover:bg-surface-sunken',
    secondary: 'bg-surface text-fg border border-border hover:bg-surface-sunken',
    accent: 'bg-accent text-on-accent hover:brightness-95',
  }[variant];
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      {...rest}
      className={cn(
        'inline-grid place-items-center transition-colors duration-fast disabled:opacity-50 disabled:cursor-not-allowed',
        size === 'sm' ? 'size-8' : 'size-10', round ? 'rounded-pill' : 'rounded-md', focusRing, v, className,
      )}
    >
      {children}
    </button>
  );
}
