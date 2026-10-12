/** Backend client. Server-Sent Events over POST (fetch + a stream reader), because EventSource cannot POST. */

export const API_BASE: string = import.meta.env.VITE_API ?? 'http://127.0.0.1:8770';

export interface Profile { id: string; name: string; provider: string; model: string; is_default: number; ready: boolean }
export interface ProjectRow { id: string; name: string; head_version_id: string | null; updated_at: string }
export interface Requirement { kind: string; text: string; supported: boolean; status: 'met' | 'unmet' | 'unsupported' | 'not_checked'; detail: string }
export interface VersionInfo {
  id: string; number: number; mode: string; prompt: string; llm: string; approach: string; summary: string; notes: string[]; created_at: string;
  requirements: Requirement[]; design: { levels: { id: string; name: string }[]; rooms: { id: string; name: string; level: string; rect: number[] }[] };
}
export interface ProjectDetail { project: ProjectRow; head: VersionInfo | null; versions: { number: number; prompt: string; summary: string; mode: string }[] }

export interface Clause { id: string; title: string; section: string; status: 'pass' | 'fail' | 'info'; measured: string; required: string; elements: string[]; guids: string[]; fix: string }
export interface Review { ruleset: string; disclaimer: string; summary: { gross_area_m2: number; levels: number; rooms: number; pass: number; fail: number; info: number }; clauses: Clause[] }
export interface QuantityRow { group: string; item: string; qty: number; unit: string; note: string }
export interface Quantities { rows: QuantityRow[]; rooms: { name: string; level: string; kind: string; area_m2: number }[]; totals: { net_area_m2: number; elements: number } }
export interface Analysis { review: Review; quantities: Quantities }

export interface RunEvent { seq: number; t: number; stage: string; message: string; data: Record<string, any> }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { headers: { 'Content-Type': 'application/json' }, ...init });
  } catch {
    throw new ApiError(0, 'Cannot reach the backend. Start it with: python -m app.main (in the backend folder).');
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* body was not JSON */ }
    throw new ApiError(res.status, String(detail));
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  health: () => request<{ ok: boolean; llm: { profile: string; provider: string; model: string }; dwg_converter: boolean }>('/api/health'),
  analysis: (id: string, n: number) => request<Analysis>(`/api/projects/${id}/versions/${n}/analysis`),
  drawingUrl: (id: string, n: number) => `${API_BASE}/api/projects/${id}/versions/${n}/drawing`,
  profiles: () => request<Profile[]>('/api/llm/profiles'),
  projects: () => request<ProjectRow[]>('/api/projects'),
  createProject: (name: string) => request<ProjectRow>('/api/projects', { method: 'POST', body: JSON.stringify({ name }) }),
  project: (id: string) => request<ProjectDetail>(`/api/projects/${id}`),
  renameProject: (id: string, name: string) => request<ProjectRow>(`/api/projects/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: 'DELETE' }),
  revert: (id: string, n: number) => request<VersionInfo>(`/api/projects/${id}/revert/${n}`, { method: 'POST' }),
  ifcUrl: (id: string, n: number) => `${API_BASE}/api/projects/${id}/versions/${n}/ifc`,
  exportUrl: (id: string, n: number, format: string) => `${API_BASE}/api/projects/${id}/versions/${n}/export?format=${format}`,
  absolute: (path: string) => (path.startsWith('http') ? path : `${API_BASE}${path}`),
};

/** Run a prompt and yield its events as they arrive. Abort with the signal. */
export async function* runPrompt(projectId: string, body: { prompt: string; base_version?: number | null; profile_id?: string | null; focus_guid?: string | null }, signal: AbortSignal): AsyncGenerator<RunEvent> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/projects/${projectId}/runs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
  } catch (e) {
    if ((e as Error).name === 'AbortError') return;
    throw new ApiError(0, 'Cannot reach the backend. Start it with: python -m app.main (in the backend folder).');
  }
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new ApiError(res.status, String(detail));
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      let cut: number;
      while ((cut = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        const data = block.split('\n').find((l) => l.startsWith('data:'));
        if (data) yield JSON.parse(data.slice(5)) as RunEvent;   // ": ping" comments carry no data line and are skipped
      }
    }
  } catch (e) {
    if ((e as Error).name !== 'AbortError') throw e;
  }
}
