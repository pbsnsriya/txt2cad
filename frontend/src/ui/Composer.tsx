import { useId, useRef, useState } from 'react';
import { ArrowUp, Plus, Square, ChevronDown } from 'lucide-react';
import { cn, focusRing } from './cn';
import { IconButton } from './Button';
import { Menu, type MenuEntry } from './Menu';

export interface ComposerProps {
  variant?: 'hero' | 'docked';
  placeholder: string;
  running?: boolean;
  disabled?: boolean;
  error?: string;
  modelLabel: string;
  modelEntries: MenuEntry[];
  onSubmit: (text: string) => void;
  onStop?: () => void;
  onAttach?: () => void;
  initialValue?: string;
  contextLabel?: string;           // what the next message is about (the element selected in the viewer)
  onClearContext?: () => void;
}

/** Enter sends, Shift+Enter inserts a newline. While running, the send button becomes Stop. */
export function Composer({ variant = 'hero', placeholder, running, disabled, error, modelLabel, modelEntries, onSubmit, onStop, onAttach, initialValue = '', contextLabel, onClearContext }: ComposerProps) {
  const [text, setText] = useState(initialValue);
  const ref = useRef<HTMLTextAreaElement>(null);
  const labelId = useId();
  const canSend = text.trim().length > 0 && !disabled && !running;

  const send = () => {
    if (!canSend) return;
    onSubmit(text.trim());
    setText('');
  };

  return (
    <div className="w-full">
      <div
        className={cn(
          'flex flex-col gap-2 border bg-surface p-3 shadow-card',
          variant === 'hero' ? 'rounded-xl min-h-32' : 'rounded-lg',
          error ? 'border-danger' : 'border-border',
          'focus-within:border-accent',
        )}
      >
        {contextLabel && (
          <div className="flex items-center gap-1 self-start rounded-pill bg-accent-soft px-2 py-0.5 text-xs text-accent-text" data-testid="context-chip">
            <span className="max-w-64 truncate">About: {contextLabel}</span>
            <button type="button" aria-label="Clear selection" onClick={onClearContext} className="rounded-pill px-1 hover:bg-accent/20">x</button>
          </div>
        )}
        <label id={labelId} htmlFor={`${labelId}-ta`} className="sr-only">Describe what to build</label>
        <textarea
          id={`${labelId}-ta`}
          ref={ref}
          rows={variant === 'hero' ? 2 : 1}
          value={text}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send();
            }
          }}
          className="w-full resize-none bg-transparent px-1 py-1 text-base text-fg placeholder:text-muted outline-none disabled:opacity-50"
        />
        <div className="flex items-center justify-between">
          <IconButton label="Attach an image" variant="secondary" round size="sm" onClick={onAttach} disabled={disabled}>
            <Plus className="size-4" aria-hidden />
          </IconButton>
          <div className="flex items-center gap-2">
            <Menu
              align="end"
              entries={modelEntries}
              trigger={
                <button type="button" className={cn('inline-flex h-8 items-center gap-1 rounded-md px-2 text-sm text-muted hover:text-fg', focusRing)}>
                  {modelLabel}
                  <ChevronDown className="size-4" aria-hidden />
                </button>
              }
            />
            {running ? (
              <IconButton label="Stop" variant="accent" round size="sm" onClick={onStop}>
                <Square className="size-3.5 fill-current" aria-hidden />
              </IconButton>
            ) : (
              <IconButton label="Send" variant="accent" round size="sm" onClick={send} disabled={!canSend}>
                <ArrowUp className="size-4" aria-hidden />
              </IconButton>
            )}
          </div>
        </div>
      </div>
      <p role={error ? 'alert' : 'status'} className={cn('mt-1 min-h-5 text-xs', error ? 'text-danger' : 'sr-only')}>
        {error ?? (running ? 'Run in progress' : '')}
      </p>
    </div>
  );
}
