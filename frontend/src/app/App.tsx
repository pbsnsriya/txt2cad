import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Box, ChevronDown, Download, FileText, FolderOpen, LayoutGrid, MessageSquare, Moon, Receipt, Ruler, ShieldCheck, Sun } from 'lucide-react';
import { ApiError, api, runPrompt, type Analysis, type Capabilities, type Profile, type ProjectDetail, type ProjectRow } from '../api/client';
import { emptyRun, reduceRun, startRun, type RunView } from '../state/run';
import { Badge } from '../ui/Badge';
import { Button, IconButton } from '../ui/Button';
import { Composer } from '../ui/Composer';
import { Menu, TooltipProvider, type MenuEntry } from '../ui/Menu';
import { ConfirmDialog, Resizer } from '../ui/Overlays';
import { EmptyState, Skeleton } from '../ui/Surface';
import { Tabs } from '../ui/Tabs';
import { SizesTab, type SizeChange } from './SizesTab';
import { Trace, VersionList } from './Assistant';
import { ViewerPane, type ViewerHandle } from './ViewerPane';
import { DrawingsTab } from './DrawingsTab';
import { ReviewTab } from './ReviewTab';
import { QuantitiesTab } from './QuantitiesTab';
import type { Picked } from '../viewer/IfcViewer';
import { HomeScreen } from './HomeScreen';
import { ProjectsSheet } from './ProjectsSheet';
import { FeedbackDialog } from './FeedbackDialog';

const STARTERS = ['Two-storey family house', 'Small office floor', 'Studio flat with a kitchen', 'Three-storey townhouse', 'Cabin with one bedroom'];
const STARTER_PROMPTS: Record<string, string> = {
  'Two-storey family house': 'Two storey house with a kitchen, living room and three bedrooms, a garage.',
  'Small office floor': 'A one storey office with a reception, a meeting room and two offices.',
  'Studio flat with a kitchen': 'A one storey studio flat with a kitchen, a living room and a bathroom.',
  'Three-storey townhouse': 'Three storey townhouse with two bedrooms, a study and a bathroom.',
  'Cabin with one bedroom': 'A small one storey cabin with one bedroom and a kitchen.',
};
const ASSISTANT_DEFAULT = 380;

/** Where a model profile sends what you type. Said in the menu, so the choice is made with the facts in front of you. */
function dataNote(p: Profile): string {
  if (p.provider === 'mock') return 'Runs on this computer. Nothing is sent anywhere.';
  let host = p.base_url;
  try { host = new URL(p.base_url).hostname; } catch { /* keep the raw value */ }
  return `${p.model || 'Model'}: your request and design are sent to ${host}`;
}

/** The tag for a picked part: its name, or its kind when it has none. */
function tagLabel(p: Picked): string {
  return p.name || p.category.replace(/^Ifc/, '') || 'Element';
}

function readStored(key: string): string | null { try { return localStorage.getItem(key); } catch { return null; } }
function writeStored(key: string, v: string): void { try { localStorage.setItem(key, v); } catch { /* storage may be blocked */ } }

export function App() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => (readStored('theme') === 'dark' ? 'dark' : 'light'));
  const [projectsOpen, setProjectsOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [assistant, setAssistant] = useState(ASSISTANT_DEFAULT);
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [backend, setBackend] = useState<{ ok: boolean; label: string }>({ ok: false, label: 'Checking...' });
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [analysing, setAnalysing] = useState(false);
  const [run, setRun] = useState<RunView>(emptyRun);
  const [viewing, setViewing] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState<ProjectRow | null>(null);
  const [tab, setTab] = useState('3d');
  const [follow, setFollow] = useState(true);
  const [selected, setSelected] = useState<Picked[]>([]);
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
        api.capabilities().then(setCaps).catch(() => undefined);          // a nicety: the app works without it
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
    try {
      await execute(project, prompt, { base: detail?.head?.number ?? null, focus: selected });
    } finally {
      submitting.current = false;
    }
  }

  /** One streamed run. Returns whether it ended with a saved version. */
  async function execute(project: ProjectRow, prompt: string, opts: { base: number | null; focus?: Picked[]; layout?: number }): Promise<boolean> {
    const ctrl = new AbortController();
    abort.current = ctrl;
    const tags = (opts.focus ?? []).map(tagLabel);
    setRun(startRun(prompt, tags));
    setBusy(true);
    let latest = startRun(prompt, tags);
    let saved = false;
    try {
      for await (const ev of runPrompt(project.id, { prompt, base_version: opts.base, profile_id: profileId, focus_guids: (opts.focus ?? []).map((f) => f.guid), layout: opts.layout ?? null }, ctrl.signal)) {
        latest = reduceRun(latest, ev);
        setRun(latest);
        if (ev.stage === 'preview') showModel(api.absolute(ev.data.url), followRef.current);
        if (ev.stage === 'finished') {
          saved = true;
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
      setBusy(false);
      if (latest.status === 'running') setRun({ ...latest, status: 'error', error: 'The run ended without a result.' });
    }
    return saved;
  }

  /** The first request built three more ways, one after the other. Each is saved as a new version; stopping ends the series. */
  async function tryLayouts(): Promise<void> {
    if (submitting.current || !detail?.head) return;
    const project = detail.project;
    const first = detail.versions.find((v) => v.number === 1) ?? { prompt: detail.head.prompt };
    const brief = first.prompt.replace(/ \[layout option [^\]]*\]$/, '');
    submitting.current = true;
    setError('');
    try {
      for (let k = 1; k <= 3; k++) {
        const fresh = await api.project(project.id);
        if (!(await execute(project, brief, { base: fresh.head?.number ?? null, layout: k }))) break;
      }
    } finally {
      submitting.current = false;
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

  /** Change sizes by hand: no model is called. Returns an error in words, or null when a new version was saved. */
  async function applySizes(change: SizeChange): Promise<string | null> {
    if (!detail?.head) return 'Build something first.';
    setBusy(true);
    try {
      await api.resize(detail.project.id, { base_version: detail.head.number, ...change });
      await openProject(detail.project.id);
      return null;
    } catch (e) {
      return (e as Error).message;
    } finally {
      setBusy(false);
    }
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
    id: p.id, title: `${p.name}${p.id === profileId ? ' (selected)' : ''}`, description: dataNote(p),
    disabledReason: p.ready ? undefined : p.model ? `Set the ${p.name} key in the backend environment` : 'Choose a model first', onSelect: () => setProfileId(p.id),
  })), [profiles, profileId]);
  const modelLabel = profiles.find((p) => p.id === profileId)?.name ?? 'Model';

  const head = detail?.head ?? null;
  const building = run.status === 'running';
  const inWorkspace = Boolean(detail) || run.status !== 'idle';
  const count = run.elements || analysis?.quantities.totals.elements || 0;
  const badge = building ? (run.elements ? `building · ${run.elements} elements` : 'building') : viewing ? `v${viewing}${count ? ` · ${count} elements` : ''}` : '';
  const exportEntries: MenuEntry[] = [
    { id: 'ifc', title: 'BIM file (.ifc)', description: 'IFC4, opens in Revit, Archicad, Navisworks', onSelect: () => download(viewing, 'ifc') },
    { id: 'dxf', title: 'Floor plans (.dxf)', description: 'one drawing per storey, named layers, metres', onSelect: () => download(viewing, 'dxf') },
    { id: 'html', title: 'Shareable page (.html)', description: 'one file to turn, zoom and look around the model in any browser, offline', onSelect: () => download(viewing, 'html') },
    { id: 'svg', title: 'Floor plans (.svg)', description: 'the same plans as a picture', onSelect: () => download(viewing, 'svg') },
    { id: 'spec', title: 'Geometry data (.json)', description: 'every element the files are built from', onSelect: () => download(viewing, 'spec_json') },
    { id: 'design', title: 'Design data (.json)', description: 'rooms, doors and windows as designed', onSelect: () => download(viewing, 'design_json') },
  ];

  return (
    <TooltipProvider>
      <div className="flex h-full flex-col bg-bg text-fg">
        <header className="flex h-[56px] shrink-0 items-center gap-2 border-b border-border px-3">
          <Button variant="secondary" size="sm" icon={<FolderOpen className="size-4" aria-hidden />} onClick={() => setProjectsOpen(true)}>Projects</Button>
          <h1 className="min-w-0 flex-1 truncate px-1 text-sm font-medium" title={detail?.project.name}>{detail?.project.name ?? 'txt2cad'}</h1>
          <span role="status"><Badge tone={backend.ok ? 'success' : 'danger'}>{backend.ok ? 'Server online' : 'Server offline'}</Badge></span>
          <Menu
            trigger={
              <Button size="sm" variant="secondary" disabled={!viewing} title={viewing ? undefined : 'Build something to export'}
                icon={<Download className="size-4" aria-hidden />}>Export<ChevronDown className="size-3.5" aria-hidden /></Button>
            }
            entries={exportEntries}
          />
          <Button variant="ghost" size="sm" icon={<MessageSquare className="size-4" aria-hidden />} className="max-md:px-2" onClick={() => setFeedbackOpen(true)}><span className="max-md:sr-only">Feedback</span></Button>
          <IconButton label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
          </IconButton>
        </header>
        {!inWorkspace ? (
          <HomeScreen starters={STARTERS} prompts={STARTER_PROMPTS} projects={projects} modelLabel={modelLabel} modelEntries={modelEntries}
            disabled={!backend.ok} error={error || undefined} onSubmit={(t) => void submit(t)} onOpen={(id) => void openProject(id)}
            capabilities={caps?.capabilities} unsupportedWords={caps?.unsupported_words} />
        ) : (
          <main className="flex min-h-0 flex-1 flex-col overflow-y-auto md:flex-row md:overflow-visible">
            <section className="relative flex h-[52vh] min-h-72 min-w-0 shrink-0 flex-col md:order-3 md:h-auto md:min-h-0 md:flex-1 md:shrink" aria-label="Model">
              <Tabs value={tab} onValueChange={setTab} className="flex h-full min-h-0 flex-col" contentClassName="min-h-0 flex-1 data-[state=active]:flex data-[state=active]:flex-col"
                items={[
                  { id: '3d', label: '3D view', icon: <Box className="size-4" aria-hidden />, keepMounted: true, content: (
                    <ViewerPane pictureName={`${(detail?.project.name ?? 'txt2cad').replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'txt2cad'}-v${viewing || 0}`} badge={badge} empty={!viewing && !building} building={building} theme={theme} onReady={onViewer} follow={follow} onFollow={setFollow} selected={selected} onPick={setSelected} />) },
                  { id: 'dr', label: 'Plans', icon: <FileText className="size-4" aria-hidden />, disabledReason: viewing ? undefined : 'Build something first',
                    content: <DrawingsTab url={detail && viewing ? `${api.drawingUrl(detail.project.id, viewing)}?v=${detail.head?.id ?? ''}` : null} onDownload={(f) => download(viewing, f)} /> },
                  { id: 'sz', label: 'Sizes', icon: <Ruler className="size-4" aria-hidden />, disabledReason: viewing ? undefined : 'Build something first',
                    content: <SizesTab head={detail?.head ?? null} busy={busy || building} onApply={applySizes} /> },
                  { id: 'cr', label: 'Design check', icon: <ShieldCheck className="size-4" aria-hidden />, disabledReason: viewing ? undefined : 'Build something first',
                    content: <ReviewTab analysis={analysis} loading={analysing} onShow={(g) => { setTab('3d'); setTimeout(() => void viewer.current?.highlight(g), 150); }} /> },
                  { id: 'cc', label: 'Quantities', icon: <Receipt className="size-4" aria-hidden />, disabledReason: viewing ? undefined : 'Build something first',
                    content: <QuantitiesTab analysis={analysis} loading={analysing} /> },
                ]} />
            </section>
            <div className="hidden md:order-2 md:flex"><Resizer side="right" label="Conversation width" value={assistant} min={300} max={640} onChange={setAssistant} onReset={() => setAssistant(ASSISTANT_DEFAULT)} /></div>
            <aside aria-label="Conversation" style={{ "--aw": `${assistant}px` } as React.CSSProperties}
              className="flex min-h-96 w-full shrink-0 flex-col border-t border-border bg-surface md:order-1 md:min-h-0 md:w-[var(--aw)] md:border-r md:border-t-0">
              <div className="flex-1 overflow-y-auto p-4 md:min-h-0">
                {detail && run.status === 'idle' && !head && <EmptyState title="Say what to build in the box below." />}
                <Trace run={run} />
                {detail && head && run.status !== 'running' && (
                  <div className="mt-4 flex flex-col gap-4">
                    {run.status === 'idle' && <p className="text-sm text-muted">{head.summary}</p>}
                    <div className="flex flex-col items-start gap-1">
                      <Button size="sm" variant="secondary" icon={<LayoutGrid className="size-4" aria-hidden />} disabled={busy || !backend.ok} onClick={() => void tryLayouts()}>
                        Try 3 other layouts
                      </Button>
                      <p className="text-xs text-muted">Builds your first request three more ways. Each one is saved as a new version.</p>
                    </div>
                    <VersionList detail={detail} viewing={viewing} busy={busy} onDownload={download} onRestore={(n) => void restore(n)}
                      onOpen={(n) => { setViewing(n); showModel(api.ifcUrl(detail.project.id, n)); }} />
                  </div>
                )}
                {run.status === 'running' && !run.phases.length && <Skeleton className="mt-4 h-16" />}
              </div>
              <div className="border-t border-border p-3">
                <Composer key={`${detail?.project.id ?? 'new'}-${initialPrompt}`} variant="docked" initialValue={initialPrompt}
                  placeholder={detail?.head ? 'What should change?' : 'Describe the building you want...'} modelLabel={modelLabel} modelEntries={modelEntries}
                  running={building} disabled={!backend.ok} error={error || undefined} suggestions={head?.suggestions} unsupportedWords={caps?.unsupported_words}
                  contexts={selected.map((s) => ({ id: s.guid, label: tagLabel(s) }))} onRemoveContext={(id) => viewer.current?.removeFromSelection(id)} onClearContext={() => viewer.current?.clearSelection()} onSubmit={(t) => void submit(t)} onStop={() => abort.current?.abort()} />
              </div>
            </aside>
          </main>
        )}
      </div>
      <FeedbackDialog open={feedbackOpen} onOpenChange={setFeedbackOpen} prompt={detail?.versions.find((v) => v.number === viewing)?.prompt} summary={detail?.versions.find((v) => v.number === viewing)?.summary} version={viewing || undefined} />
      <ProjectsSheet open={projectsOpen} onOpenChange={setProjectsOpen} projects={projects} currentId={detail?.project.id}
        onOpen={(id) => void openProject(id)} onNew={() => void newSession()} onDelete={setDeleting} />
      <ConfirmDialog open={Boolean(deleting)} onOpenChange={(o) => !o && setDeleting(null)} title="Delete this project?"
        body={`"${deleting?.name ?? ''}" and all its versions will be removed from this computer.`} confirmLabel="Delete project" onConfirm={() => void confirmDelete()} />
    </TooltipProvider>
  );
}
