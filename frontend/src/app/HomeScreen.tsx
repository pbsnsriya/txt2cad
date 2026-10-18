import { History } from 'lucide-react';
import type { Capability, ProjectRow } from '../api/client';
import { Chip } from '../ui/Badge';
import { Composer } from '../ui/Composer';
import type { MenuEntry } from '../ui/Menu';
import { ListRow } from '../ui/Surface';
import { useState } from 'react';

/** The first screen: one big prompt box, starter chips, and the sessions already on this computer. */
export function HomeScreen({ starters, prompts, projects, modelLabel, modelEntries, disabled, error, onSubmit, onOpen, capabilities = [], unsupportedWords }: {
  starters: string[]; prompts: Record<string, string>; projects: ProjectRow[]; modelLabel: string; modelEntries: MenuEntry[];
  disabled: boolean; error?: string; onSubmit: (text: string) => void; onOpen: (id: string) => void; capabilities?: Capability[]; unsupportedWords?: Record<string, string>;
}) {
  const [seed, setSeed] = useState({ text: '', n: 0 });
  return (
    <main className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto px-6 pb-10 pt-[12vh]">
      <div className="flex w-full max-w-[758px] flex-col gap-6">
        <h2 className="text-center text-display font-bold">Start with a sentence</h2>
        <Composer key={seed.n} variant="hero" initialValue={seed.text} placeholder="Describe the building you want: storeys, rooms, what goes where..."
          modelLabel={modelLabel} modelEntries={modelEntries} disabled={disabled} error={error} onSubmit={onSubmit} unsupportedWords={unsupportedWords} />
        <div role="group" aria-label="Starter prompts" className="flex flex-wrap justify-center gap-2">
          {starters.map((s) => <Chip key={s} onClick={() => setSeed({ text: prompts[s], n: seed.n + 1 })}>{s}</Chip>)}
        </div>
        {capabilities.length > 0 && (
          <details className="mx-auto max-w-[620px] text-xs text-muted" data-testid="capabilities">
            <summary className="cursor-pointer text-center hover:text-fg">What it builds today</summary>
            <div className="mt-2 flex flex-col gap-3 text-left">
              {([['yes', 'Builds today'], ['partly', 'Partly'], ['no', 'Not built yet']] as const).map(([status, title]) => (
                <section key={status} aria-label={title}>
                  <h3 className="font-medium text-fg">{title}</h3>
                  <ul className="mt-1 list-disc space-y-1 pl-5">
                    {capabilities.filter((c) => c.status === status).map((c) => <li key={c.id}><span className="text-fg">{c.label}.</span> {c.note}</li>)}
                  </ul>
                </section>
              ))}
            </div>
          </details>
        )}
        <details className="mx-auto max-w-[620px] text-xs text-muted">
          <summary className="cursor-pointer text-center hover:text-fg">Where does my data go?</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-left">
            <li>There is no account. Projects, versions and files are saved on this computer only.</li>
            <li>Practice mode builds offline and sends nothing anywhere.</li>
            <li>Gemini: your request, the current design and the element you picked are sent to Google, using your own key. Google's terms for that key apply.
              The key is read from the backend's environment and never stored in the database or sent to the browser.</li>
          </ul>
        </details>
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
