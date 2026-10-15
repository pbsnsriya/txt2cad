import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Box, FileText, Home as HomeIcon, Moon, PanelLeft, Plus, Receipt, ShieldCheck, Sun, Trash2 } from 'lucide-react';
import { ApiError, api, runPrompt, type Analysis, type Profile, type ProjectDetail, type ProjectRow } from '../api/client';
import { emptyRun, reduceRun, startRun, type RunView } from '../state/run';
import { Badge } from '../ui/Badge';
import { Button, IconButton } from '../ui/Button';
import { Composer } from '../ui/Composer';
import { SplitButton, TooltipProvider, type MenuEntry } from '../ui/Menu';
import { ConfirmDialog, Resizer } from '../ui/Overlays';
import { EmptyState, ListRow, Skeleton } from '../ui/Surface';
import { Tabs } from '../ui/Tabs';
import { Trace, VersionList } from './Assistant';
import { ViewerPane, type ViewerHandle } from './ViewerPane';
import { DrawingsTab } from './DrawingsTab';
import { ReviewTab } from './ReviewTab';
import { QuantitiesTab } from './QuantitiesTab';
import type { Picked } from '../viewer/IfcViewer';
import { HomeScreen } from './HomeScreen';

const STARTERS = ['Two-storey family house', 'Small office floor', 'Studio flat with a kitchen', 'Three-storey townhouse', 'Cabin with one bedroom'];
const STARTER_PROMPTS: Record<string, string> = {
  'Two-storey family house': 'Two storey house with a kitchen, living room and three bedrooms, a garage.',
  'Small office floor': 'A one storey office with a reception, a meeting room and two offices.',
  'Studio flat with a kitchen': 'A one storey studio flat with a kitchen, a living room and a bathroom.',
  'Three-storey townhouse': 'Three storey townhouse with two bedrooms, a study and a bathroom.',
  'Cabin with one bedroom': 'A small one storey cabin with one bedroom and a kitchen.',
};
const ASSISTANT_DEFAULT = 390;

function readStored(key: string): string | null { try { return localStorage.getItem(key); } catch { return null; } }
function writeStored(key: string, v: string): void { try { localStorage.setItem(key, v); } catch { /* storage may be blocked */ } }

export function App() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => (readStored('theme') === 'dark' ? 'dark' : 'light'));
  const [sidebar, setSidebar] = useState(() => window.innerWidth >= 768);   // below 768px the session list is an overlay, closed by default
  const [assistant, setAssistant] = useState(ASSISTANT_DEFAULT);
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [backend, setBackend] = useState<{ ok: boolean; label: string }>({ ok: false, label: 'Checking...' });
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analysing, setAnalysing] = useState(false);
  const [run, setRun] = useState<RunView>(emptyRun);
  const [viewing, setViewing] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState<ProjectRow | null>(null);
  const [tab, setTab] = useState('3d');
  const [follow, setFollow] = useState(true);
  const [selected, setSelected] = useState<Picked | null>(null);
  const followRef = useRef(true);
  followRef.current = follow;
  const submitting = useRef(false);
  const viewer = useRef<ViewerHandle | null>(null);
  const pendingModel = useRef<string | null>(null);   // the viewer unmounts on Home; remember what to show when it comes back
  const abort = useRef<AbortController | null>(null);
  const initialPrompt = '';

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    writeStored('theme', theme);
  }, [theme]);

  const refreshProjects = useCallback(async () => setProjects(await api.projects()), []);
  useEffect(() => {
    (async () => {
      try {
        const [h, p, list] = await Promise.all([api.health(), api.profiles(), api.projects()]);
        setBackend({ ok: true, label: `${h.llm.profile}` });
        setProfiles(p);
        setProfileId((cur) => cur ?? p.find((x) => x.is_default)?.id ?? null);
        setProjects(list);
        const last = readStored('project');
        if (last && list.some((x) => x.id === last)) await openProject(last);
      } catch (e) {
        setBackend({ ok: false, label: 'Not connected' });
        setError((e as Error).message);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The design check and quantities belong to the version on screen; fetch them when it changes.
  const projectId = detail?.project.id;
  useEffect(() => {
    if (!projectId || !viewing) { setAnalysis(null); return; }
    let live = true;
    setAnalysing(true);
    api.analysis(projectId, viewing).then((a) => live && setAnalysis(a)).catch(() => live && setAnalysis(null)).finally(() => live && setAnalysing(false));
    return () => { live = false; };
  }, [projectId, viewing, detail?.head?.number]);

  const onViewer = useCallback((h: ViewerHandle | null) => {
    viewer.current = h;
    if (h && pendingModel.current) void h.load(pendingModel.current, true);
  }, []);
  /** refit = bring the whole model back into frame (while it is being built, and for the finished result). */
  const showModel = (url: string, refit = false) => { pendingModel.current = url; void viewer.current?.load(url, refit); };
  const clearModel = () => { pendingModel.current = null; viewer.current?.clear(); };

  async function openProject(id: string, number?: number, refit = false): Promise<void> {
    const d = await api.project(id);
    setDetail(d);
    writeStored('project', id);
    setRun(emptyRun);
    const n = number ?? d.head?.number ?? 0;
    setViewing(n);
    if (n) showModel(api.ifcUrl(id, n), refit);
    else clearModel();
  }

  async function newSession(): Promise<void> {
    abort.current?.abort();
    setDetail(null); setRun(emptyRun); setViewing(0); setError('');
    clearModel();
    try { localStorage.removeItem('project'); } catch { /* ignore */ }
  }

  async function submit(prompt: string): Promise<void> {
    if (submitting.current) { console.warn('submit ignored: a run is already in progress', new Error().stack); return; }
    submitting.current = true;
    setError('');
    let project = detail?.project;
    try {
      if (!project) {
        project = await api.createProject(prompt.slice(0, 60));
        setDetail({ project, head: null, versions: [] });
        writeStored('project', project.id);
      }
    } catch (e) { setError((e as Error).message); submitting.current = false; return; }
    const ctrl = new AbortController();
    abort.current = ctrl;
    setRun(startRun(prompt));
    setBusy(true);
    let latest = startRun(prompt);
    try {
      for await (const ev of runPrompt(project.id, { prompt, base_version: detail?.head?.number ?? null, profile_id: profileId, focus_guid: selected?.guid || null }, ctrl.signal)) {
        latest = reduceRun(latest, ev);
        setRun(latest);
        if (ev.stage === 'partial') showModel(api.absolute(ev.data.url), followRef.current);
        if (ev.stage === 'done') {
          await openProject(project.id, undefined, followRef.current);
          setRun(latest);
          void refreshProjects();
        }
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message;
      latest = { ...latest, status: 'error', error: msg };
      setRun(latest);
      setError(msg);
    } finally {
      submitting.current = false;
      setBusy(false);
      if (latest.status === 'running') setRun({ ...latest, status: 'error', error: 'The run ended without a result.' });
    }
  }

  function download(n: number, format: string): void {
    if (!detail) return;
    const a = document.createElement('a');
    a.href = api.exportUrl(detail.project.id, n, format);
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function restore(n: number): Promise<void> {
    if (!detail) return;
    setBusy(true);
    try { await api.revert(detail.project.id, n); await openProject(detail.project.id); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function confirmDelete(): Promise<void> {
    if (!deleting) return;
    const id = deleting.id;
    setDeleting(null);
    try { await api.deleteProject(id); if (detail?.project.id === id) await newSession(); await refreshProjects(); } catch (e) { setError((e as Error).message); }
  }

  const modelEntries: MenuEntry[] = useMemo(() => profiles.map((p) => ({
    id: p.id, title: `${p.name}${p.id === profileId ? ' (selected)' : ''}`, description: p.model || (p.provider === 'mock' ? 'No network, simple designs' : 'Set a model'),
    disabledReason: p.ready ? undefined : p.model ? `Set the ${p.name} key in the backend environment` : 'Choose a model first', onSelect: () => setProfileId(p.id),
  })), [profiles, profileId]);
  const modelLabel = profiles.find((p) => p.id === profileId)?.name ?? 'Model';

  const head = detail?.head ?? null;
  const building = run.status === 'running';
  const inWorkspace = Boolean(detail) || run.status !== 'idle';
  const count = run.elements || analysis?.quantities.totals.elements || 0;
  const badge = building ? (run.elements ? `building · ${run.elements} elements` : 'building') : viewing ? `v${viewing}${count ? ` · ${count} elements` : ''}` : '';
  const exportEntries: MenuEntry[] = [
    { id: 'ifc', title: 'IFC model', description: 'IFC4 for Revit, Archicad, Navisworks', onSelect: () => download(viewing, 'ifc') },
    { id: 'dxf', title: 'CAD plans (.dxf)', description: 'every level on named layers, in metres', onSelect: () => download(viewing, 'dxf') },
    { id: 'spec', title: 'Geometry spec (.json)', description: 'every element the files were built from', onSelect: () => download(viewing, 'spec_json') },
    { id: 'design', title: 'Design record (.json)', description: 'rooms, doors and windows as designed', onSelect: () => download(viewing, 'design_json') },
    { id: 'svg', title: 'Plans (.svg)', description: 'the floor plans as a vector picture', onSelect: () => download(viewing, 'svg') },
  ];

  return (
    <TooltipProvider>
      <div className="flex h-full bg-bg text-fg">
        {sidebar && (
          <nav aria-label="Sessions" className="flex w-[270px] shrink-0 flex-col gap-3 border-r border-border bg-bg p-3 max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-40 max-md:shadow-pop">
            <div className="flex items-center justify-between px-1 py-1"><span className="text-lg font-bold">txt2cad</span></div>
            <Button variant="secondary" icon={<Plus className="size-4" aria-hidden />} onClick={() => void newSession()} className="justify-start">New session</Button>
            <h2 className="mt-2 px-1 text-xs font-medium text-muted">Past sessions</h2>
            <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
              {projects.length === 0 && <p className="px-1 text-sm text-muted">Nothing yet. Describe a building to start.</p>}
              {projects.map((p) => (
                <div key={p.id} className="group flex items-center gap-1">
                  <div className="min-w-0 flex-1"><ListRow title={p.name} selected={detail?.project.id === p.id} onClick={() => void openProject(p.id)} /></div>
                  <IconButton label={`Delete session ${p.name}`} size="sm" onClick={() => setDeleting(p)}><Trash2 className="size-4" aria-hidden /></IconButton>
                </div>
              ))}
            </div>
            <div className="rounded-lg border border-border bg-surface p-3 text-sm">
              <div className="flex items-center justify-between"><span className="font-medium">Backend</span><Badge tone={backend.ok ? 'success' : 'danger'}>{backend.ok ? 'Connected' : 'Offline'}</Badge></div>
              <p className="mt-1 text-xs text-muted">Model: {modelLabel}</p>
            </div>
          </nav>
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-[59px] shrink-0 items-center gap-2 border-b border-border px-3">
            <IconButton label={sidebar ? 'Hide sessions' : 'Show sessions'} onClick={() => setSidebar((s) => !s)}><PanelLeft className="size-4" aria-hidden /></IconButton>
            <HomeIcon className="size-4 text-muted" aria-hidden />
            <span className="text-sm text-muted">/</span>
            <h1 className="min-w-0 flex-1 truncate text-sm font-medium" title={detail?.project.name}>{detail?.project.name ?? 'New session'}</h1>
            <SplitButton label="Export IFC" onMain={() => download(viewing, 'ifc')} entries={exportEntries} disabled={!viewing} disabledReason="Nothing to export yet" />
            <IconButton label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
              {theme === 'dark' ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
            </IconButton>
          </header>
          {!inWorkspace ? (
            <HomeScreen starters={STARTERS} prompts={STARTER_PROMPTS} projects={projects} modelLabel={modelLabel} modelEntries={modelEntries}
              disabled={!backend.ok} error={error || undefined} onSubmit={(t) => void submit(t)} onOpen={(id) => void openProject(id)} />
          ) : (
          <main className="flex min-h-0 flex-1 flex-col md:flex-row overflow-y-auto md:overflow-visible">
            <section className="relative flex h-[52vh] min-h-72 shrink-0 min-w-0 flex-col md:h-auto md:min-h-0 md:flex-1 md:shrink" aria-label="Model">
              <Tabs value={tab} onValueChange={setTab} className="flex h-full min-h-0 flex-col" contentClassName="min-h-0 flex-1 data-[state=active]:flex data-[state=active]:flex-col"
                items={[
                  { id: '3d', label: '3D model', icon: <Box className="size-4" aria-hidden />, keepMounted: true, content: (
                    <ViewerPane badge={badge} empty={!viewing && !building} building={building} theme={theme} onReady={onViewer} follow={follow} onFollow={setFollow} selected={selected} onPick={setSelected} />) },
                  { id: 'dr', label: 'Drawings', icon: <FileText className="size-4" aria-hidden />, disabledReason: viewing ? undefined : 'Build something first',
                    content: <DrawingsTab url={detail && viewing ? `${api.drawingUrl(detail.project.id, viewing)}?v=${detail.head?.id ?? ''}` : null} onDownload={(f) => download(viewing, f)} /> },
                  { id: 'cr', label: 'Design check', icon: <ShieldCheck className="size-4" aria-hidden />, disabledReason: viewing ? undefined : 'Build something first',
                    content: <ReviewTab analysis={analysis} loading={analysing} onShow={(g) => { setTab('3d'); setTimeout(() => void viewer.current?.highlight(g), 150); }} /> },
                  { id: 'cc', label: 'Quantities', icon: <Receipt className="size-4" aria-hidden />, disabledReason: viewing ? undefined : 'Build something first',
                    content: <QuantitiesTab analysis={analysis} loading={analysing} /> },
                ]} />
            </section>
            <div className="hidden md:flex"><Resizer label="Assistant width" value={assistant} min={300} max={640} onChange={setAssistant} onReset={() => setAssistant(ASSISTANT_DEFAULT)} /></div>
            <aside aria-label="Assistant" style={{ "--aw": `${assistant}px` } as React.CSSProperties} className="flex min-h-96 w-full shrink-0 flex-col border-t border-border bg-surface md:min-h-0 md:w-[var(--aw)] md:border-l md:border-t-0">
              <div className="flex-1 overflow-y-auto p-4 md:min-h-0">
                {detail && run.status === 'idle' && !head && <EmptyState title="Describe what to build below." />}
                <Trace run={run} />
                {detail && head && run.status !== 'running' && (
                  <div className="mt-4 flex flex-col gap-4">
                    {run.status === 'idle' && <p className="text-sm text-muted">{head.summary}</p>}
                    <VersionList detail={detail} viewing={viewing} busy={busy} onDownload={download} onRestore={(n) => void restore(n)}
                      onOpen={(n) => { setViewing(n); showModel(api.ifcUrl(detail.project.id, n)); }} />
                  </div>
                )}
                {run.status === 'running' && !run.phases.length && <Skeleton className="mt-4 h-16" />}
              </div>
              <div className="border-t border-border p-3">
                <Composer key={`${detail?.project.id ?? 'new'}-${initialPrompt}`} variant="docked" initialValue={initialPrompt}
                  placeholder={detail?.head ? 'Describe a change...' : 'Describe a building...'} modelLabel={modelLabel} modelEntries={modelEntries}
                  running={building} disabled={!backend.ok} error={error || undefined}
                  contextLabel={selected ? (selected.name || selected.category.replace(/^Ifc/, '')) : undefined} onClearContext={() => viewer.current?.clearSelection()} onSubmit={(t) => void submit(t)} onStop={() => abort.current?.abort()} />
              </div>
            </aside>
          </main>
          )}
        </div>
      </div>
      <ConfirmDialog open={Boolean(deleting)} onOpenChange={(o) => !o && setDeleting(null)} title="Delete this session?"
        body={`"${deleting?.name ?? ''}" and all its versions will be removed from this computer.`} confirmLabel="Delete session" onConfirm={() => void confirmDelete()} />
    </TooltipProvider>
  );
}
