/** Folds the backend's event stream into what the assistant panel shows. Pure, so it is easy to test. */
import type { Requirement, RunEvent } from '../api/client';

export interface StepLine { text: string; why?: string; ok: boolean }
export interface PhaseLog { name: string; steps: StepLine[]; errors: string[] }
export interface RunView {
  status: 'idle' | 'running' | 'done' | 'error';
  prompt: string;
  model: string;
  checklist: { text: string; supported: boolean }[];
  approach: string;
  phases: PhaseLog[];
  draft: string;
  verify: Requirement[];
  verifyText: string;
  error: string;
  previews: number;
  elements: number;
  summary: string;
  notes: string[];
  ifcUrl: string;
  number: number;
  seconds: number;
}

export const emptyRun: RunView = {
  status: 'idle', prompt: '', model: '', checklist: [], approach: '', phases: [], draft: '', verify: [], verifyText: '', error: '',
  previews: 0, elements: 0, summary: '', notes: [], ifcUrl: '', number: 0, seconds: 0,
};

export function startRun(prompt: string): RunView {
  return { ...emptyRun, status: 'running', prompt };
}

export function reduceRun(run: RunView, ev: RunEvent): RunView {
  const d = ev.data;
  const next: RunView = { ...run, seconds: ev.t };
  switch (ev.stage) {
    case 'build': return { ...next, model: d.model ?? run.model };
    case 'requirements': return { ...next, checklist: (d.items ?? []).map((r: any) => ({ text: r.text, supported: r.supported !== false })) };
    case 'approach': return { ...next, approach: d.text ?? ev.message };
    case 'draft': return { ...next, draft: d.text ?? '' };
    case 'step': {
      const phases = run.phases.map((p) => ({ ...p, steps: [...p.steps], errors: [...p.errors] }));
      // A rejected step has no phase of its own: show it under the phase of the latest accepted step.
      const name: string = d.phase ?? phases[phases.length - 1]?.name ?? 'Other';
      let phase = phases.find((p) => p.name === name);
      if (!phase) { phase = { name, steps: [], errors: [] }; phases.push(phase); }
      if (d.ok) phase.steps.push({ text: ev.message, why: d.why ?? undefined, ok: true });
      else phase.errors.push(ev.message);
      return { ...next, phases, draft: '' };
    }
    case 'partial': return { ...next, previews: d.n ?? run.previews + 1, elements: d.elements ?? run.elements };
    case 'verify': return { ...next, verify: d.items ?? [], verifyText: ev.message };
    case 'done': return { ...next, status: 'done', summary: ev.message, notes: d.notes ?? [], ifcUrl: d.ifc_url ?? '', number: d.number ?? 0, elements: d.elements ?? run.elements, draft: '' };
    case 'error': return { ...next, status: 'error', error: ev.message, draft: '' };
    default: return next;
  }
}
