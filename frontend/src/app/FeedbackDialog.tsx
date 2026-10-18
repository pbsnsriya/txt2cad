import { useMemo, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { ExternalLink, MessageSquare, X } from 'lucide-react';
import { Button, IconButton } from '../ui/Button';
import { CheckboxField } from '../ui/Inputs';
import { cn, focusRing } from '../ui/cn';
import { buildFeedback } from '../lib/feedback';

/** Tell the maker what worked and what did not. Nothing is sent from here: it builds the text, shows all of it, and opens a prefilled GitHub issue that the person submits. */
export function FeedbackDialog({ open, onOpenChange, prompt, summary, version }: {
  open: boolean; onOpenChange: (o: boolean) => void; prompt?: string; summary?: string; version?: number;
}) {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const [include, setInclude] = useState(false);
  const [copied, setCopied] = useState(false);
  const canInclude = Boolean(prompt || summary);
  const fb = useMemo(() => buildFeedback({ rating, comment, include: include && canInclude, prompt, summary, version }), [rating, comment, include, canInclude, prompt, summary, version]);

  async function copy(): Promise<void> {
    try { await navigator.clipboard.writeText(`${fb.title}\n\n${fb.body}`); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { setCopied(false); }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-fg/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[90vh] w-[min(94vw,34rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-3 overflow-y-auto rounded-lg border border-border bg-surface p-5 shadow-pop">
          <div className="flex items-center justify-between">
            <Dialog.Title className="flex items-center gap-2 text-lg font-semibold"><MessageSquare className="size-5 text-muted" aria-hidden />Tell us how it went</Dialog.Title>
            <Dialog.Close asChild><IconButton label="Close feedback" size="sm"><X className="size-4" aria-hidden /></IconButton></Dialog.Close>
          </div>
          <Dialog.Description className="text-sm text-muted">
            Nothing is sent from here. This writes a note you can read below, and the button opens it as a GitHub issue for you to look over and submit.
          </Dialog.Description>
          <div role="radiogroup" aria-label="How useful was it?" className="flex items-center gap-1">
            <span className="mr-2 text-sm font-medium">How useful was it?</span>
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} type="button" role="radio" aria-checked={rating === n} aria-label={`${n} of 5`} onClick={() => setRating(n)}
                className={cn('size-9 rounded-md border text-sm', rating === n ? 'border-accent bg-accent text-on-accent' : 'border-border bg-surface hover:bg-surface-sunken', focusRing)}>{n}</button>
            ))}
          </div>
          <label className="sr-only" htmlFor="feedback-text">What happened?</label>
          <textarea id="feedback-text" rows={4} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="What did you ask for, what did you get, what was wrong or good?"
            className={cn('w-full rounded-md border border-input bg-surface px-3 py-2 text-sm placeholder:text-muted', focusRing)} />
          <CheckboxField label={canInclude ? 'Include my last request and what was built' : 'Nothing has been built yet to include'} checked={include && canInclude} disabled={!canInclude} onCheckedChange={setInclude} />
          <div>
            <p className="mb-1 text-xs font-medium text-muted">This is everything that will go in the note:</p>
            <pre data-testid="feedback-preview" className="max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-surface-sunken p-2 text-xs">{fb.title}{'\n\n'}{fb.body}</pre>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="secondary" onClick={() => void copy()}>{copied ? 'Copied' : 'Copy text'}</Button>
            <a href={fb.url} target="_blank" rel="noopener noreferrer" data-testid="feedback-link"
              className={cn('inline-flex h-10 items-center gap-2 rounded-md bg-accent px-4 text-sm font-medium text-on-accent hover:brightness-95', focusRing)}>
              Open as a GitHub issue<ExternalLink className="size-4" aria-hidden />
            </a>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
