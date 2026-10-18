/** That Open wrapper: one world, one model at a time, newest-load-wins. The only file that knows That Open's API. */

import * as OBC from '@thatopen/components';
import * as FRAGS from '@thatopen/fragments';
import * as THREE from 'three';

export type ViewName = 'top' | 'bottom' | 'front' | 'back' | 'left' | 'right' | 'iso';

export interface LoadStats { box: THREE.Box3 }
export interface Picked { guid: string; name: string; category: string }

/** Parts of a model that are not things a person points at: the voids cut for doors and windows. */
const NOT_PICKABLE = new Set(['IfcOpeningElement']);
const MAX_PICKED = 80;

export class IfcViewer {
  private components = new OBC.Components();
  private world!: OBC.SimpleWorld<OBC.SimpleScene, OBC.SimpleCamera, OBC.SimpleRenderer>;
  private fragments!: OBC.FragmentsManager;
  private loader!: OBC.IfcLoader;
  private model: FRAGS.FragmentsModel | null = null;
  private ready: Promise<void>;
  private pending = 0;                       // newest request id; older loads are dropped when they finish
  private framed = false;
  private disposed = false;               // React StrictMode mounts, disposes and re-mounts; async init must notice
  private resizeObserver: ResizeObserver;
  onLoaded?: (stats: LoadStats) => void;
  onPick?: (picked: Picked[]) => void;
  private downAt: { x: number; y: number } | null = null;
  private picked = new Map<number, Picked>();      // what is selected, by the model's local id
  private areaMode = false;
  private rectStart: { x: number; y: number } | null = null;
  private rectEl: HTMLDivElement | null = null;

  constructor(private container: HTMLElement) {
    this.ready = this.init();
    this.resizeObserver = new ResizeObserver(() => this.world?.renderer?.resize());
    this.resizeObserver.observe(container);
    // A click is a press and release that did not move: dragging orbits the camera and must not select anything.
    // In area mode a drag draws a box instead and selects whatever the box touches.
    container.addEventListener('pointerdown', (e) => {
      if (this.areaMode) { this.beginBox(e); return; }
      this.downAt = { x: e.clientX, y: e.clientY };
    });
    container.addEventListener('pointermove', (e) => { if (this.rectStart) this.moveBox(e); });
    container.addEventListener('pointerup', (e) => {
      if (this.rectStart) { void this.endBox(e); return; }
      const d = this.downAt;
      this.downAt = null;
      if (d && Math.hypot(e.clientX - d.x, e.clientY - d.y) < 5) void this.pick(e);
    });
  }

  private async init(): Promise<void> {
    const worlds = this.components.get(OBC.Worlds);
    this.world = worlds.create<OBC.SimpleScene, OBC.SimpleCamera, OBC.SimpleRenderer>();
    this.world.scene = new OBC.SimpleScene(this.components);
    this.world.renderer = new OBC.SimpleRenderer(this.components, this.container);
    this.world.camera = new OBC.SimpleCamera(this.components);
    this.components.init();
    this.world.scene.setup();
    this.applyTheme();
    this.world.renderer.three.localClippingEnabled = true;
    this.world.camera.controls.setLookAt(14, 12, 14, 0, 0, 0);
    this.components.get(OBC.Grids).create(this.world);
    this.fragments = this.components.get(OBC.FragmentsManager);
    // The library's own getWorker() downloads this file from unpkg.com on every start. It is shipped with the app instead (scripts/copy-wasm.mjs).
    const workerUrl = '/vendor/fragments-worker.mjs';
    if (this.disposed) return;
    this.fragments.init(workerUrl);
    // Fragments throws "No camera initialized" if asked to update before any model has been given the camera.
    this.world.camera.controls.addEventListener('update', () => { if (this.fragments.list.size > 0) this.fragments.core.update(); });
    this.fragments.list.onItemSet.add(({ value: model }) => {
      model.useCamera(this.world.camera.three);
      this.world.scene.three.add(model.object);
      this.fragments.core.update(true);
    });
    this.loader = this.components.get(OBC.IfcLoader);
    await this.loader.setup({ autoSetWasm: false, wasm: { path: '/wasm/', absolute: true } });
  }


  /** Click: select the part under the pointer. Shift, Ctrl or Cmd adds it to the selection, or takes it out if it is already in. */
  private async pick(e: PointerEvent): Promise<void> {
    const model = this.model;
    const renderer = this.world.renderer;
    if (!model || !renderer) return;
    const hit = await model.raycast({ camera: this.world.camera.three, mouse: new THREE.Vector2(e.clientX, e.clientY), dom: renderer.three.domElement });
    const add = e.shiftKey || e.ctrlKey || e.metaKey;
    if (!hit) { if (!add) await this.setPicked([]); return; }
    if (add && this.picked.has(hit.localId)) { this.picked.delete(hit.localId); await this.showPicked(); return; }
    const [item] = await this.describe([hit.localId]);
    if (!item) return;
    if (!add) this.picked.clear();
    this.picked.set(hit.localId, item.picked);
    await this.showPicked();
  }

  /** Name, class and GlobalId of some local ids, leaving out the voids. */
  private async describe(ids: number[]): Promise<{ id: number; picked: Picked }[]> {
    const model = this.model;
    if (!model || !ids.length) return [];
    const [guids, data] = await Promise.all([model.getGuidsByLocalIds(ids), model.getItemsData(ids)]);
    const attr = (row: unknown, k: string): string => String((row as Record<string, { value?: unknown }> | undefined)?.[k]?.value ?? '');
    const out: { id: number; picked: Picked }[] = [];
    ids.forEach((id, i) => {
      const category = attr(data[i], '_category');
      if (NOT_PICKABLE.has(category) || !guids[i]) return;
      out.push({ id, picked: { guid: guids[i] as string, name: attr(data[i], 'Name'), category } });
    });
    return out;
  }

  private async setPicked(items: { id: number; picked: Picked }[]): Promise<void> {
    this.picked = new Map(items.slice(0, MAX_PICKED).map((i) => [i.id, i.picked]));
    await this.showPicked();
  }

  /** Paint the selection and tell the page what it is. */
  private async showPicked(): Promise<void> {
    await this.fragments.resetHighlight();
    const model = this.model;
    if (model && this.picked.size) {
      const accent = getComputedStyle(document.documentElement).getPropertyValue('--tk-accent').trim() || '#2f5bea';
      await this.fragments.highlight({ color: new THREE.Color(accent), renderedFaces: FRAGS.RenderedFaces.ONE, opacity: 1, transparent: false }, { [model.modelId]: new Set(this.picked.keys()) });
    }
    this.onPick?.([...this.picked.values()]);
  }

  // --- area selection: drag a box, take everything it touches -------------------------------------------------------------
  setAreaMode(on: boolean): void {
    this.areaMode = on;
    if (this.world?.camera) this.world.camera.controls.enabled = !on;      // the drag draws a box instead of turning the model
    this.container.style.cursor = on ? 'crosshair' : '';
    if (!on) this.removeBox();
  }

  private beginBox(e: PointerEvent): void {
    const r = this.container.getBoundingClientRect();
    this.rectStart = { x: e.clientX, y: e.clientY };
    const el = document.createElement('div');
    el.setAttribute('data-testid', 'area-box');
    el.style.cssText = 'position:absolute;pointer-events:none;border:2px dashed var(--tk-accent,#2f5bea);background:rgba(47,91,234,0.12);z-index:5;';
    el.style.left = `${e.clientX - r.left}px`;
    el.style.top = `${e.clientY - r.top}px`;
    this.container.appendChild(el);
    this.rectEl = el;
  }

  private moveBox(e: PointerEvent): void {
    if (!this.rectStart || !this.rectEl) return;
    const r = this.container.getBoundingClientRect();
    this.rectEl.style.left = `${Math.min(this.rectStart.x, e.clientX) - r.left}px`;
    this.rectEl.style.top = `${Math.min(this.rectStart.y, e.clientY) - r.top}px`;
    this.rectEl.style.width = `${Math.abs(e.clientX - this.rectStart.x)}px`;
    this.rectEl.style.height = `${Math.abs(e.clientY - this.rectStart.y)}px`;
  }

  private removeBox(): void {
    this.rectEl?.remove();
    this.rectEl = null;
    this.rectStart = null;
  }

  private async endBox(e: PointerEvent): Promise<void> {
    const start = this.rectStart;
    this.removeBox();
    const model = this.model;
    const renderer = this.world.renderer;
    if (!start || !model || !renderer) return;
    if (Math.hypot(e.clientX - start.x, e.clientY - start.y) < 6) return;       // a click in area mode selects nothing
    const result = await model.rectangleRaycast({
      camera: this.world.camera.three, dom: renderer.three.domElement, fullyIncluded: false,
      topLeft: new THREE.Vector2(Math.min(start.x, e.clientX), Math.min(start.y, e.clientY)),
      bottomRight: new THREE.Vector2(Math.max(start.x, e.clientX), Math.max(start.y, e.clientY)),
    });
    const found = await this.describe(result?.localIds ?? []);
    if (e.shiftKey || e.ctrlKey || e.metaKey) for (const f of found) this.picked.set(f.id, f.picked);
    else this.picked = new Map(found.map((f) => [f.id, f.picked]));
    while (this.picked.size > MAX_PICKED) this.picked.delete(this.picked.keys().next().value as number);
    await this.showPicked();
  }

  /** Take one part out of the selection (the tag in the chat was closed). */
  async deselect(guid: string): Promise<void> {
    for (const [id, p] of this.picked) if (p.guid === guid) this.picked.delete(id);
    await this.showPicked();
  }

  /** Highlight the elements with these IFC GlobalIds (for "Show in model"). Returns how many were found. */
  async highlightGuids(guids: string[]): Promise<number> {
    const model = this.model;
    if (!model || !guids.length) return 0;
    await this.fragments.resetHighlight();
    const ids = (await model.getLocalIdsByGuids(guids)).filter((x): x is number => x !== null);
    if (!ids.length) return 0;
    const accent = getComputedStyle(document.documentElement).getPropertyValue('--tk-accent').trim() || '#2f5bea';
    await this.fragments.highlight({ color: new THREE.Color(accent), renderedFaces: FRAGS.RenderedFaces.ONE, opacity: 1, transparent: false }, { [model.modelId]: new Set(ids) });
    return ids.length;
  }

  /** The 3D view as a PNG data URL, as it looks right now (drawn again first, because a canvas that is not kept cannot be read after the frame). */
  snapshot(): string | null {
    const renderer = this.world?.renderer?.three;
    if (!renderer || !this.model) return null;
    renderer.render(this.world.scene.three, this.world.camera.three);
    return renderer.domElement.toDataURL('image/png');
  }

  clearSelection(): void {
    this.picked.clear();
    void this.fragments?.resetHighlight();
    this.onPick?.([]);
  }

  /** Background follows the app theme token, read at call time so a theme switch only needs applyTheme(). */
  applyTheme(): void {
    const css = getComputedStyle(document.documentElement).getPropertyValue('--tk-viewer-bg').trim();
    if (css && this.world?.scene) this.world.scene.three.background = new THREE.Color(css);
  }

  /** Load an IFC from a URL. If a newer load starts first, this one is discarded. */
  async load(url: string, name = 'model', refit = false): Promise<boolean> {
    await this.ready;
    if (this.disposed) return false;
    const mine = ++this.pending;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`could not download the model (HTTP ${res.status})`);
    const bytes = new Uint8Array(await res.arrayBuffer());
    if (mine !== this.pending) return false;
    const next = await this.loader.load(bytes, true, `${name}-${mine}`);
    if (mine !== this.pending) {
      await this.fragments.core.disposeModel(next.modelId);
      return false;
    }
    const previous = this.model;
    this.model = next;
    this.picked.clear();
    this.onPick?.([]);                      // a new model: any old selection is gone
    if (previous) {
      this.world.scene.three.remove(previous.object);
      await this.fragments.core.disposeModel(previous.modelId);
    }
    if (!this.framed || refit) { this.fit(); this.framed = true; }   // refit while following a build, so the growing model stays in frame
    this.onLoaded?.({ box: next.box });
    return true;
  }

  clear(): void {
    this.pending++;
    this.framed = false;
    if (this.model) {
      const m = this.model;
      this.model = null;
      this.world.scene.three.remove(m.object);
      void this.fragments.core.disposeModel(m.modelId);
    }
  }

  private boxCentre(): { c: THREE.Vector3; r: number } {
    const box = this.model?.box ?? new THREE.Box3(new THREE.Vector3(-5, 0, -5), new THREE.Vector3(5, 5, 5));
    const c = box.getCenter(new THREE.Vector3());
    return { c, r: Math.max(box.getSize(new THREE.Vector3()).length() * 0.9, 6) };
  }

  fit(): void { this.setView('iso'); }

  setView(view: ViewName): void {
    const { c, r } = this.boxCentre();
    const dir: Record<ViewName, [number, number, number]> = {
      top: [0, 1, 0.001], bottom: [0, -1, 0.001], front: [0, 0.2, 1], back: [0, 0.2, -1], left: [-1, 0.2, 0], right: [1, 0.2, 0], iso: [1, 0.8, 1],
    };
    const [dx, dy, dz] = dir[view];
    const v = new THREE.Vector3(dx, dy, dz).normalize().multiplyScalar(r);
    void this.world.camera.controls.setLookAt(c.x + v.x, c.y + v.y, c.z + v.z, c.x, c.y, c.z, true);
  }

  /** fraction 1 = full height (no cut). Cuts horizontally at that share of the model's height. */
  setSection(fraction: number): number | null {
    if (!this.model) return null;
    const box = this.model.box;
    const y = box.min.y + (box.max.y - box.min.y) * fraction;
    const renderer = this.world.renderer;
    if (!renderer) return null;
    renderer.three.clippingPlanes = fraction >= 0.999 ? [] : [new THREE.Plane(new THREE.Vector3(0, -1, 0), y)];
    return y - box.min.y;
  }

  height(): number { return this.model ? this.model.box.max.y - this.model.box.min.y : 0; }

  dispose(): void {
    this.disposed = true;
    this.resizeObserver.disconnect();
    this.pending++;
    this.components.dispose();
    this.container.replaceChildren();
  }
}
