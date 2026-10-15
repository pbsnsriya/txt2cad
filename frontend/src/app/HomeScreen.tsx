import { History } from 'lucide-react';
import type { ProjectRow } from '../api/client';
import { Chip } from '../ui/Badge';
import { Composer } from '../ui/Composer';
import type { MenuEntry } from '../ui/Menu';
import { ListRow } from '../ui/Surface';
import { useState } from 'react';

/** The first screen: one big prompt box, starter chips, and the sessions already on this computer. */
export function HomeScreen({ starters, prompts, projects, modelLabel, modelEntries, disabled, error, onSubmit, onOpen }: {
  starters: string[]; prompts: Record<string, string>; projects: ProjectRow[]; modelLabel: string; modelEntries: MenuEntry[];
  disabled: boolean; error?: string; onSubmit: (text: string) => void; onOpen: (id: string) => void;
}) {
  const [seed, setSeed] = useState({ text: '', n: 0 });
  return (
    <main className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto px-6 pb-10 pt-[12vh]">
      <div className="flex w-full max-w-[758px] flex-col gap-6">
        <h2 className="text-center text-display font-bold">Start with a sentence</h2>
        <Composer key={seed.n} variant="hero" initialValue={seed.text} placeholder="Describe the building you want: storeys, rooms, what goes where..."
          modelLabel={modelLabel} modelEntries={modelEntries} disabled={disabled} error={error} onSubmit={onSubmit} />
        <div role="group" aria-label="Starter prompts" className="flex flex-wrap justify-center gap-2">
          {starters.map((s) => <Chip key={s} onClick={() => setSeed({ text: prompts[s], n: seed.n + 1 })}>{s}</Chip>)}
        </div>
        {projects.length > 0 && (
          <section aria-label="Pick up where you left off" className="mt-6 flex flex-col gap-2">
            <h3 className="flex items-center gap-2 text-xs font-medium text-muted"><History className="size-3.5" aria-hidden />Recent sessions</h3>
            {projects.slice(0, 5).map((p) => <ListRow key={p.id} title={p.name} onClick={() => onOpen(p.id)} />)}
          </section>
        )}
      </div>
    </main>
  );
}
