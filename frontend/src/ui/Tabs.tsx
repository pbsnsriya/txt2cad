import type { ReactNode } from 'react';
import * as RadixTabs from '@radix-ui/react-tabs';
import { cn, focusRing } from './cn';

export interface TabItem {
  id: string;
  label: string;
  icon?: ReactNode;
  disabledReason?: string; // disabled tabs stay focusable and explain why
  content: ReactNode;
  keepMounted?: boolean;   // keep the panel alive while another tab is open (a WebGL canvas must not be torn down)
}

/** Radix Tabs: tablist / tab / tabpanel roles and arrow-key navigation come for free. */
export function Tabs({ items, value, onValueChange, className, contentClassName = 'p-4' }: {
  items: TabItem[]; value: string; onValueChange: (id: string) => void; className?: string; contentClassName?: string;
}) {
  return (
    <RadixTabs.Root value={value} onValueChange={onValueChange} className={className}>
      <RadixTabs.List aria-label="Views" className="flex gap-1 border-b border-border bg-bg px-3 py-2 overflow-x-auto">
        {items.map((t) => (
          <RadixTabs.Trigger
            key={t.id}
            value={t.id}
            disabled={Boolean(t.disabledReason)}
            title={t.disabledReason}
            className={cn(
              'inline-flex h-10 items-center gap-2 rounded-md border border-transparent px-3 text-sm text-muted whitespace-nowrap',
              'hover:text-fg disabled:opacity-50 disabled:cursor-not-allowed', focusRing,
              'data-[state=active]:bg-surface data-[state=active]:border-border data-[state=active]:text-fg',
            )}
          >
            {t.icon}
            {t.label}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {items.map((t) => (
        <RadixTabs.Content key={t.id} value={t.id} forceMount={t.keepMounted ? true : undefined} className={cn('outline-none data-[state=inactive]:hidden', contentClassName)}>
          {t.content}
        </RadixTabs.Content>
      ))}
    </RadixTabs.Root>
  );
}
