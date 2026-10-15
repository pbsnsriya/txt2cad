import * as Dialog from '@radix-ui/react-dialog';
import { FolderOpen, Plus, Trash2, X } from 'lucide-react';
import type { ProjectRow } from '../api/client';
import { Button, IconButton } from '../ui/Button';
import { ListRow } from '../ui/Surface';

/** The list of projects, as a sheet that slides in from the left. It replaces a permanent sidebar so the work area gets the whole width. */
export function ProjectsSheet({ open, onOpenChange, projects, currentId, onOpen, onNew, onDelete }: {
  open: boolean; onOpenChange: (open: boolean) => void; projects: ProjectRow[]; currentId?: string;
  onOpen: (id: string) => void; onNew: () => void; onDelete: (p: ProjectRow) => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-fg/30" />
        <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex w-[min(92vw,22rem)] flex-col gap-3 border-r border-border bg-surface p-4 shadow-pop">
          <div className="flex items-center justify-between">
            <Dialog.Title className="flex items-center gap-2 text-lg font-semibold"><FolderOpen className="size-5 text-muted" aria-hidden />Projects</Dialog.Title>
            <Dialog.Close asChild><IconButton label="Close projects" size="sm"><X className="size-4" aria-hidden /></IconButton></Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">Open an earlier project, start a new one, or delete one.</Dialog.Description>
          <Button variant="primary" icon={<Plus className="size-4" aria-hidden />} onClick={() => { onNew(); onOpenChange(false); }}>New project</Button>
          <ul className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto" aria-label="Your projects">
            {projects.length === 0 && <li className="px-1 text-sm text-muted">No projects yet. Describe a building to start one.</li>}
            {projects.map((p) => (
              <li key={p.id} className="flex items-center gap-1">
                <div className="min-w-0 flex-1"><ListRow title={p.name} selected={currentId === p.id} onClick={() => { onOpen(p.id); onOpenChange(false); }} /></div>
                <IconButton label={`Delete project ${p.name}`} size="sm" onClick={() => { onOpenChange(false); onDelete(p); }}><Trash2 className="size-4" aria-hidden /></IconButton>
              </li>
            ))}
          </ul>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
