import { useEffect, useState, type ReactNode } from 'react';
import { Box, FileText, Moon, Play, ShieldCheck, Sun, Receipt, Trash2, Wifi } from 'lucide-react';
import { Button, IconButton } from '../ui/Button';
import { Badge, Chip } from '../ui/Badge';
import { Card, EmptyState, ListRow, Skeleton, Spinner, Table } from '../ui/Surface';
import { Menu, SplitButton, TooltipProvider, WithTooltip } from '../ui/Menu';
import { Tabs } from '../ui/Tabs';
import { CheckboxField, Input, SliderField, Textarea } from '../ui/Inputs';
import { Composer } from '../ui/Composer';
import { TraceSection } from '../ui/Trace';
import { ConfirmDialog, Resizer, Toast } from '../ui/Overlays';

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="flex flex-wrap items-start gap-3">{children}</div>
    </section>
  );
}

const exportEntries = [
  { id: 'ifc', title: 'IFC model', description: 'IFC4 for Revit, Archicad, Navisworks' },
  { id: 'dxf', title: 'CAD plans (.dxf)', description: 'every level on named layers' },
  { id: 'svg', title: 'Plans (.svg)', description: 'the floor plans as a vector picture' },
];

export function DesignPage() {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => (new URLSearchParams(location.search).get('theme') === 'dark' ? 'dark' : 'light'));
  const [tab, setTab] = useState('3d');
  const [follow, setFollow] = useState(true);
  const [cut, setCut] = useState(5.7);
  const [panel, setPanel] = useState(390);
  const [confirm, setConfirm] = useState(false);
  const [toasts, setToasts] = useState(['info', 'danger'] as const);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('theme', theme); } catch { /* storage may be blocked */ }
  }, [theme]);

  return (
    <TooltipProvider>
      <main className="mx-auto flex max-w-5xl flex-col gap-8 p-6">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold">Design system check</h1>
            <p className="text-sm text-muted">Every primitive and state, from tokens only. Theme: {theme}.</p>
          </div>
          <IconButton label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} variant="secondary" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
          </IconButton>
        </header>

        <Block title="Button">
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger" icon={<Trash2 className="size-4" aria-hidden />}>Danger</Button>
          <Button variant="primary" loading>Loading</Button>
          <Button variant="secondary" disabled>Disabled</Button>
          <Button size="sm">Small</Button>
          <WithTooltip text="Tooltip on hover and focus"><IconButton label="Play recorded run"><Play className="size-4" aria-hidden /></IconButton></WithTooltip>
          <SplitButton label="Export IFC" onMain={() => {}} entries={exportEntries} />
          <SplitButton label="Export IFC" onMain={() => {}} entries={exportEntries} disabled disabledReason="Nothing to export yet" />
        </Block>

        <Block title="Badge and Chip">
          <Badge>Neutral</Badge>
          <Badge tone="info">v1 final</Badge>
          <Badge tone="success" icon={<Wifi className="size-3" aria-hidden />}>Connected</Badge>
          <Badge tone="warning" mono>preview 6 · 118 elements</Badge>
          <Badge tone="danger">Failed</Badge>
          <Chip>Highway bridge</Chip>
          <Chip selected>Rail station</Chip>
          <Chip disabled>Substation</Chip>
        </Block>

        <Block title="Composer (hero, docked, running, error)">
          <div className="w-full max-w-[758px]">
            <Composer placeholder="Describe a building or an asset..." modelLabel="Mock model" modelEntries={[{ id: 'mock', title: 'Mock model', description: 'No network' }, { id: 'local', title: 'Local model' }, { id: 'gemini', title: 'Gemini' }]} onSubmit={() => {}} />
          </div>
          <div className="w-full max-w-md"><Composer variant="docked" placeholder="Describe a change..." modelLabel="Local" modelEntries={[]} running onSubmit={() => {}} /></div>
          <div className="w-full max-w-md"><Composer variant="docked" placeholder="Describe a change..." modelLabel="Local" modelEntries={[]} error="The model did not answer. Check the endpoint in settings." onSubmit={() => {}} /></div>
        </Block>

        <Block title="Tabs, ListRow, Table">
          <div className="w-full rounded-lg border border-border bg-surface">
            <Tabs
              value={tab} onValueChange={setTab}
              items={[
                { id: '3d', label: '3D model', icon: <Box className="size-4" aria-hidden />, content: <p className="text-sm text-muted">Viewer goes here.</p> },
                { id: 'dr', label: 'Drawings', icon: <FileText className="size-4" aria-hidden />, content: <p className="text-sm">Sheets.</p> },
                { id: 'cr', label: 'Code review', icon: <ShieldCheck className="size-4" aria-hidden />, disabledReason: 'Run a prompt first', content: null },
                { id: 'cc', label: 'Cost & carbon', icon: <Receipt className="size-4" aria-hidden />, disabledReason: 'Run a prompt first', content: null },
              ]}
            />
          </div>
          <div className="flex w-full max-w-md flex-col gap-2">
            <ListRow icon={<Play className="size-4" />} title="A two storey primary school for 180 pupils with a hall, a library and eight classrooms" meta="9 min" />
            <ListRow icon={<Play className="size-4" />} title="Selected session" meta="now" selected />
          </div>
          <div className="w-full max-w-md rounded-lg border border-border bg-surface">
            <Table caption="IFC class counts" head={['Class', 'Count']} rows={[['IfcWall', 29], ['IfcWindow', 11], ['IfcStair', 1]]} />
          </div>
        </Block>

        <Block title="Form controls">
          <div className="w-64"><Input label="Project name" placeholder="Untitled" /></div>
          <div className="w-64"><Input label="Endpoint" defaultValue="http://" error="Enter a full https:// or http:// address." /></div>
          <div className="w-64"><Input label="Locked" defaultValue="read only" readOnly /></div>
          <div className="w-64"><Textarea label="Notes" placeholder="Notes" rows={2} /></div>
          <CheckboxField label="Follow build" checked={follow} onCheckedChange={setFollow} />
          <div className="w-64"><SliderField label="Section height" value={cut} min={0} max={12} onChange={setCut} valueText={`cut at ${cut.toFixed(1)} m`} /><p className="text-xs text-muted">cut at {cut.toFixed(1)} m</p></div>
        </Block>

        <Block title="Trace (pending, active, done, rejected)">
          <Card className="w-full max-w-xl"><div className="flex flex-col gap-4">
            <TraceSection title="Reading the brief" state="done" rationale="About 197 m² over two plates. A dwelling, so the residential code applies." steps={['Level L1 added', 'Level L2 added']} />
            <TraceSection title="Floor plates" state="active" liveLine="Cutting a window in the kitchen" />
            <TraceSection title="Envelope" state="rejected" error="window: wall 'north' of 'kitchen' is interior. Exterior sides are E and S." />
            <TraceSection title="Review" state="pending" />
          </div></Card>
        </Block>

        <Block title="Card, Spinner, Skeleton, EmptyState">
          <Card variant="flat" className="w-56">Flat</Card>
          <Card variant="raised" className="w-56">Raised</Card>
          <Card variant="sunken" className="w-56">Sunken</Card>
          <Card selected className="w-56">Selected</Card>
          <Spinner label="Loading model..." />
          <div className="flex w-56 flex-col gap-2"><Skeleton className="h-24" /><Skeleton className="h-4 w-2/3" /></div>
          <Card className="w-72"><EmptyState title="Nothing to export yet" action={<Button size="sm">Start a prompt</Button>} /></Card>
        </Block>

        <Block title="Toast, Dialog, Resizer, Menu">
          <div className="flex w-full max-w-md flex-col gap-2">
            {toasts.map((t) => (
              <Toast key={t} tone={t} onDismiss={() => setToasts((all) => all.filter((x) => x !== t) as unknown as typeof toasts)}>
                {t === 'info' ? 'Exported plans.dxf' : 'Export failed. The model has no levels.'}
              </Toast>
            ))}
          </div>
          <Button onClick={() => setConfirm(true)}>Delete session...</Button>
          <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Delete this session?" body="The project and all its versions are removed from this computer." confirmLabel="Delete session" onConfirm={() => setConfirm(false)} />
          <div className="flex h-16 w-72 items-stretch rounded-md border border-border bg-surface">
            <div className="grid flex-1 place-items-center text-sm text-muted">viewer</div>
            <Resizer label="Assistant width" value={panel} min={280} max={560} onChange={setPanel} onReset={() => setPanel(390)} />
            <div className="grid w-20 place-items-center text-xs text-muted">{panel}px</div>
          </div>
          <Menu trigger={<Button>Open menu</Button>} align="start" entries={exportEntries} />
        </Block>
      </main>
    </TooltipProvider>
  );
}
