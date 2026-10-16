import type { ReactNode } from 'react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import * as Tooltip from '@radix-ui/react-tooltip';
import { ChevronDown, Download } from 'lucide-react';
import { cn, focusRing } from './cn';
import { Button } from './Button';

export interface MenuEntry {
  id: string;
  title: string;
  description?: string;
  disabledReason?: string; // when set the entry is disabled and the reason is shown under it
  onSelect?: () => void;
}

/** Dropdown with a title and one-line description per entry. Radix gives menu roles, arrow keys and type-ahead. */
export function Menu({ trigger, entries, align = 'end' }: { trigger: ReactNode; entries: MenuEntry[]; align?: 'start' | 'end' }) {
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>{trigger}</DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align={align}
          sideOffset={6}
          className="z-50 w-72 max-h-[70vh] overflow-auto rounded-lg border border-border bg-surface p-1 shadow-pop"
        >
          {entries.map((e) => (
            <DropdownMenu.Item
              key={e.id}
              disabled={Boolean(e.disabledReason)}
              onSelect={e.onSelect}
              className={cn(
                'flex flex-col rounded-md px-3 py-2 text-sm outline-none cursor-pointer',
                'data-[highlighted]:bg-surface-sunken data-[disabled]:opacity-60 data-[disabled]:cursor-not-allowed',
              )}
            >
              <span className="font-medium text-fg">{e.title}</span>
              {e.description && <span className="text-xs text-muted">{e.description}</span>}
              {e.disabledReason && <span className="text-xs text-muted">{e.disabledReason}</span>}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

/** Main action plus a caret that opens a Menu. Disabled until there is something to export. */
export function SplitButton({ label, onMain, entries, disabled, disabledReason }: {
  label: string; onMain: () => void; entries: MenuEntry[]; disabled?: boolean; disabledReason?: string;
}) {
  return (
    <div className="inline-flex rounded-md border border-border bg-surface" title={disabled ? disabledReason : undefined}>
      <Button variant="ghost" className="rounded-r-none" icon={<Download className="size-4" aria-hidden />} onClick={onMain} disabled={disabled}>
        {label}
      </Button>
      <Menu
        trigger={
          <button
            type="button"
            aria-label="Other export formats"
            disabled={disabled}
            className={cn('grid w-9 place-items-center rounded-r-md border-l border-border hover:bg-surface-sunken disabled:opacity-50', focusRing)}
          >
            <ChevronDown className="size-4" aria-hidden />
          </button>
        }
        entries={entries}
      />
    </div>
  );
}

export function TooltipProvider({ children }: { children: ReactNode }) {
  return <Tooltip.Provider delayDuration={400}>{children}</Tooltip.Provider>;
}

export function WithTooltip({ text, children }: { text: string; children: ReactNode }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content sideOffset={6} className="z-50 rounded-md bg-fg px-2 py-1 text-xs text-bg">
          {text}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
