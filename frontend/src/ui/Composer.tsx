import { useId, useRef, useState } from 'react';
import { ArrowUp, Plus, Square, ChevronDown } from 'lucide-react';
import { cn, focusRing } from './cn';
import { IconButton } from './Button';
import { Menu, type MenuEntry } from './Menu';
import { findUnsupported } from '../lib/unsupported';

const MAX_TAGS = 5;

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
  contexts?: { id: string; label: string }[];   // what the next message is about: the parts picked in the 3D view, one tag each
  onRemoveContext?: (id: string) => void;
  suggestions?: string[];          // follow-up requests worth trying; picking one fills the box and does not send
  unsupportedWords?: Record<string, string>;   // things that cannot be built yet; named under the box while typing
  onClearContext?: () => void;
}

/** Enter sends, Shift+Enter inserts a newline. While running, the send button becomes Stop. */
export function Composer({ variant = 'hero', placeholder, running, disabled, error, modelLabel, modelEntries, onSubmit, onStop, onAttach, initialValue = '', contexts = [], onRemoveContext, onClearContext, suggestions = [], unsupportedWords }: ComposerProps) {
  const [allTags, setAllTags] = useState(false);
  const [text, setText] = useState(initialValue);
  const ref = useRef<HTMLTextAreaElement>(null);
  const labelId = useId();
  const canSend = text.trim().length > 0 && !disabled && !running;
  const notBuilt = unsupportedWords ? findUnsupported(text, unsupportedWords) : [];

  const send = () => {
    if (!canSend) return;
    onSubmit(text.trim());
    setText('');
  };

  const pick = (s: string) => {
    setText(s);
    ref.current?.focus();
  };

  return (
    <div className="w-full">
      {suggestions.length > 0 && !running && (
        <div role="group" aria-label="Suggested next requests" className="mb-2 flex flex-wrap gap-1.5" data-testid="suggestions">
          {suggestions.map((s) => (
            <button key={s} type="button" onClick={() => pick(s)} disabled={disabled}
              className={cn('rounded-pill border border-border bg-surface px-2.5 py-1 text-xs text-muted hover:border-accent hover:text-fg disabled:opacity-50', focusRing)}>
              {s}
            </button>
          ))}
        </div>
      )}
      <div
        className={cn(
          'flex flex-col gap-2 border bg-surface p-3 shadow-card',
          variant === 'hero' ? 'rounded-xl min-h-32' : 'rounded-lg',
          error ? 'border-danger' : 'border-border',
          'focus-within:border-accent',
        )}
      >
        {contexts.length > 0 && (
          <div className="flex flex-wrap items-center gap-1 self-start text-xs" data-testid="context-chip" aria-label="What your message is about">
            <span className="text-muted">Re:</span>
            {(allTags ? contexts : contexts.slice(0, MAX_TAGS)).map((c) => (
              <span key={c.id} className="flex items-center gap-1 rounded-pill bg-accent-soft px-2 py-0.5 text-accent-text" data-testid="tag">
                <span className="max-w-48 truncate" title={c.label}>{c.label}</span>
                <button type="button" aria-label={`Unpick ${c.label}`} onClick={() => onRemoveContext?.(c.id)} className="rounded-pill px-1 hover:bg-accent/20">x</button>
              </span>
            ))}
            {contexts.length > MAX_TAGS && (
              <button type="button" onClick={() => setAllTags(!allTags)} className={cn('rounded-pill px-2 py-0.5 text-muted hover:text-fg', focusRing)}>
                {allTags ? 'Show fewer' : `+${contexts.length - MAX_TAGS} more`}
              </button>
            )}
            {contexts.length > 1 && (
              <button type="button" onClick={onClearContext} className={cn('rounded-pill px-2 py-0.5 text-muted underline hover:text-fg', focusRing)}>Unpick all</button>
            )}
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
      {notBuilt.length > 0 && !error && (
        <p className="mt-1 text-xs text-muted" data-testid="unsupported-note">Not built yet: {notBuilt.join(', ')}. The result will say so; everything else is built.</p>
      )}
      <p role={error ? 'alert' : 'status'} className={cn('mt-1 min-h-5 text-xs', error ? 'text-danger' : 'sr-only')}>
        {error ?? (running ? 'Run in progress' : '')}
      </p>
    </div>
  );
}
