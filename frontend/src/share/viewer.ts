import {
  AmbientLight, Box3, BoxGeometry, BufferAttribute, BufferGeometry, Color, DirectionalLight, DoubleSide, EdgesGeometry, GridHelper, Group, HemisphereLight, LineBasicMaterial, LineSegments, Mesh,
  MeshStandardMaterial, OrthographicCamera, PerspectiveCamera, Raycaster, Scene, Sphere, Vector2, Vector3, WebGLRenderer,
} from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { floats, uints, type ModelData } from './data';
import { CATEGORIES, INSIDE, cameraOffset, ease, fitDistance, isShown, orthoHeight, roomShown, subtitle, TYPE_LABELS, viewById, VIEWS, type Category, type Showing } from './logic';

const FOV = 42;
const EDGE_ANGLE = 28;

interface Entry { item: ModelData['elements'][number]; meshes: Mesh[]; lines: LineSegments[]; bounds: Box3 }

export interface ShareViewer {
  view(): { name: string; projection: 'perspective' | 'orthographic'; position: number[]; target: number[]; distance: number };
  setView(id: string): void;
  setProjection(p: 'perspective' | 'orthographic'): void;
  visibleCount(): number;
  totalCount(): number;
  selected(): string | null;
}

const $ = <T extends HTMLElement>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`the page is missing #${id}`);
  return el as T;
};

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function startViewer(data: ModelData): ShareViewer {
  const stage = $('stage');
  const canvas = $<HTMLCanvasElement>('scene');
  const labelsBox = $('labels');
  const info = $('info');

  // --- the scene ---------------------------------------------------------------------------------------------------------------------------
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  // A graphics driver can drop the drawing surface (a sleeping laptop, a busy GPU). Let the browser give it back, then draw again.
  canvas.addEventListener('webglcontextlost', (ev) => ev.preventDefault());
  canvas.addEventListener('webglcontextrestored', () => { dirty = true; });
  const scene = new Scene();
  scene.add(new HemisphereLight(0xffffff, 0x9aa3b2, 1.55));
  scene.add(new AmbientLight(0xffffff, 0.35));
  const sun = new DirectionalLight(0xffffff, 1.9);
  scene.add(sun);

  const model = new Group();
  model.rotation.x = -Math.PI / 2;                                                  // the model is z up; three.js is y up
  scene.add(model);

  const entries: Entry[] = [];
  const meshOwner = new Map<Mesh, Entry>();
  const edgeMaterial = new LineBasicMaterial({ color: 0x2b303a, transparent: true, opacity: 0.55 });
  for (const item of data.elements) {
    const entry: Entry = { item, meshes: [], lines: [], bounds: new Box3() };
    for (const part of item.parts) {
      const geometry = new BufferGeometry();
      geometry.setAttribute('position', new BufferAttribute(floats(part.p), 3));
      geometry.setIndex(new BufferAttribute(uints(part.i), 1));
      const flat = geometry.toNonIndexed();                                         // flat shading: a wall keeps its crisp edges
      geometry.dispose();
      flat.computeVertexNormals();
      flat.computeBoundingBox();
      const material = new MeshStandardMaterial({ color: new Color(part.c[0], part.c[1], part.c[2]), roughness: 0.88, metalness: 0, side: DoubleSide,
                                                   transparent: part.o < 1, opacity: part.o, depthWrite: part.o >= 1 });
      const mesh = new Mesh(flat, material);
      mesh.renderOrder = part.o < 1 ? 2 : 0;
      model.add(mesh);
      entry.meshes.push(mesh);
      meshOwner.set(mesh, entry);
      if (part.o >= 1) {
        const edges = new LineSegments(new EdgesGeometry(flat, EDGE_ANGLE), edgeMaterial);
        model.add(edges);
        entry.lines.push(edges);
      }
      entry.bounds.union(flat.boundingBox as Box3);
    }
    entries.push(entry);
  }
  model.updateMatrixWorld(true);
  const box = new Box3().setFromObject(model);
  const sphere = box.getBoundingSphere(new Sphere());
  const radius = Math.max(sphere.radius, 2);
  const centre = sphere.center.clone();

  const ground = new Group();
  const size = Math.ceil(radius * 6 / 5) * 5;
  const grid = new GridHelper(size, Math.round(size / 1), 0x8b95a5, 0xc5ccd8);
  (grid.material as LineBasicMaterial).transparent = true;
  (grid.material as LineBasicMaterial).opacity = 0.45;
  grid.position.set(centre.x, box.min.y - 0.01, centre.z);
  const plate = new Mesh(new BoxGeometry(size, 0.02, size), new MeshStandardMaterial({ color: 0xe9edf3, roughness: 1, transparent: true, opacity: 0.55 }));
  plate.position.set(centre.x, box.min.y - 0.03, centre.z);
  ground.add(plate, grid);
  scene.add(ground);
  sun.position.set(centre.x + radius * 1.4, centre.y + radius * 2.4, centre.z + radius * 1.8);
  sun.target.position.copy(centre);
  scene.add(sun.target);

  // --- cameras and controls ---------------------------------------------------------------------------------------------------------------
  let aspect = 1.6;
  const perspective = new PerspectiveCamera(FOV, aspect, 0.1, radius * 40);
  const orthographic = new OrthographicCamera(-1, 1, 1, -1, -radius * 40, radius * 40);
  let projection: 'perspective' | 'orthographic' = 'perspective';
  let camera: PerspectiveCamera | OrthographicCamera = perspective;
  let controls!: OrbitControls;
  let viewName = 'perspective';
  let dirty = true;

  function makeControls(): void {
    const target = controls ? controls.target.clone() : centre.clone();
    controls?.dispose();
    controls = new OrbitControls(camera, canvas);
    controls.target.copy(target);
    controls.enableDamping = true;
    controls.dampingFactor = 0.09;
    controls.rotateSpeed = 0.8;
    controls.zoomSpeed = 0.9;
    controls.panSpeed = 0.9;
    controls.screenSpacePanning = true;
    controls.minDistance = Math.max(radius * 0.08, 0.5);
    controls.maxDistance = radius * 12;
    controls.minZoom = 0.05;
    controls.maxZoom = 80;
    controls.addEventListener('change', () => { dirty = true; if (!flight) { viewName = 'free'; markViews(); } });
    controls.update();
  }

  function distanceNow(): number {
    return camera === perspective ? camera.position.distanceTo(controls.target) : (orthographic.top - orthographic.bottom) / 2 / Math.tan((FOV * Math.PI) / 360) / orthographic.zoom;
  }

  function sizeOrtho(distance: number): void {
    const h = orthoHeight(distance, FOV);
    orthographic.left = (-h * aspect) / 2; orthographic.right = (h * aspect) / 2; orthographic.top = h / 2; orthographic.bottom = -h / 2;
    orthographic.zoom = 1;
    orthographic.updateProjectionMatrix();
  }

  function resize(): void {
    const w = Math.max(stage.clientWidth, 1), h = Math.max(stage.clientHeight, 1);
    renderer.setSize(w, h, false);
    aspect = w / h;
    perspective.aspect = aspect;
    perspective.updateProjectionMatrix();
    if (projection === 'orthographic') {
      const keepZoom = orthographic.zoom, height = (orthographic.top - orthographic.bottom) * 1;
      orthographic.left = (-height * aspect) / 2; orthographic.right = (height * aspect) / 2;
      orthographic.zoom = keepZoom;
      orthographic.updateProjectionMatrix();
    }
    dirty = true;
  }

  // Moving the camera: a short eased flight, or at once when the person prefers less motion.
  let flight: { from: { p: Vector3; t: Vector3; z: number }; to: { p: Vector3; t: Vector3; z: number }; start: number; ms: number } | null = null;
  function flyTo(position: Vector3, target: Vector3, zoom = camera.zoom): void {
    makeControls();                                                                  // new controls carry no leftover swing from the last drag, which would nudge the camera after it arrives
    const to = { p: position.clone(), t: target.clone(), z: zoom };
    if (reducedMotion()) {
      camera.position.copy(to.p); controls.target.copy(to.t); camera.zoom = to.z; camera.updateProjectionMatrix(); controls.update(); dirty = true;
      return;
    }
    flight = { from: { p: camera.position.clone(), t: controls.target.clone(), z: camera.zoom }, to, start: performance.now(), ms: 520 };
  }

  function homeDistance(): number {
    return fitDistance(radius, FOV, aspect);
  }

  function setView(id: string): void {
    const v = viewById(id);
    const d = homeDistance();
    const offset = cameraOffset(d, v.azimuth, v.elevation);
    if (projection === 'orthographic') sizeOrtho(d);
    flyTo(new Vector3(centre.x + offset[0], centre.y + offset[1], centre.z + offset[2]), centre, projection === 'orthographic' ? 1 : camera.zoom);
    viewName = v.id;
    markViews();
  }

  function setProjection(p: 'perspective' | 'orthographic'): void {
    if (p === projection) return;
    const d = distanceNow();
    const dir = camera.position.clone().sub(controls.target).normalize();
    const target = controls.target.clone();
    projection = p;
    camera = p === 'perspective' ? perspective : orthographic;
    if (p === 'orthographic') sizeOrtho(d);
    camera.position.copy(target).addScaledVector(dir, p === 'perspective' ? d : radius * 8);
    camera.lookAt(target);
    makeControls();
    controls.target.copy(target);
    controls.update();
    resize();
    markProjection();
    dirty = true;
  }

  // --- what is shown ----------------------------------------------------------------------------------------------------------------------
  const showing: Showing = { upTo: null, categories: new Set<Category>(CATEGORIES.map((c) => c.id)) };
  let withGround = true;
  let withLabels = true;

  function applyVisibility(): void {
    for (const e of entries) {
      const on = isShown(e.item, showing);
      for (const m of e.meshes) m.visible = on;
      for (const l of e.lines) l.visible = on;
    }
    ground.visible = withGround;
    occluders.length = 0;
    for (const e of entries) if (e.meshes[0]?.visible) for (const m of e.meshes) if ((m.material as MeshStandardMaterial).opacity >= 1) occluders.push(m);
    if (hovered && !isShown(hovered.item, showing)) setHover(null);
    if (picked && !isShown(picked.item, showing)) pick(null);
    dirty = true;
    updateLabels(true);
  }

  // --- labels -----------------------------------------------------------------------------------------------------------------------------
  const labelEls = data.rooms.map((r) => {
    const el = document.createElement('span');
    el.className = 'label';
    el.textContent = r.name;
    labelsBox.appendChild(el);
    return el;
  });
  const tmp = new Vector3();
  const world = new Vector3();
  const occluders: Mesh[] = [];                                                     // what can hide a room name: every shown, opaque part
  const occlusionRay = new Raycaster();
  function updateLabels(force = false): void {
    if (!force && !dirty) return;
    const w = stage.clientWidth, h = stage.clientHeight;
    camera.updateMatrixWorld();
    data.rooms.forEach((r, i) => {
      const el = labelEls[i];
      if (!withLabels || !roomShown(r, showing)) { el.hidden = true; return; }
      world.set(r.c[0], r.c[1], r.c[2]).applyMatrix4(model.matrixWorld);
      tmp.copy(world).project(camera);
      let visible = tmp.z > -1 && tmp.z < 1 && Math.abs(tmp.x) < 1.05 && Math.abs(tmp.y) < 1.05;
      if (visible) {                                                                // a name is shown only if its room can be seen: nothing opaque between it and the camera
        occlusionRay.setFromCamera(new Vector2(tmp.x, tmp.y), camera);
        occlusionRay.far = world.clone().sub(occlusionRay.ray.origin).dot(occlusionRay.ray.direction) - 0.1;
        visible = occlusionRay.far <= 0 || occlusionRay.intersectObjects(occluders, false).length === 0;
      }
      el.hidden = !visible;
      if (visible) el.style.transform = `translate(-50%, -50%) translate(${((tmp.x + 1) / 2) * w}px, ${((1 - tmp.y) / 2) * h}px)`;
    });
  }

  // --- picking ----------------------------------------------------------------------------------------------------------------------------
  const raycaster = new Raycaster();
  const pointer = new Vector2();
  let hovered: Entry | null = null;
  let picked: Entry | null = null;
  const HIGHLIGHT = new Color(0x2f6df6);

  function setEmissive(e: Entry | null, on: boolean): void {
    if (!e) return;
    for (const m of e.meshes) { const mat = m.material as MeshStandardMaterial; mat.emissive.set(on ? HIGHLIGHT : 0x000000); mat.emissiveIntensity = on ? 0.5 : 1; }
  }
  function describe(e: Entry): string {
    const level = e.item.lv >= 0 ? data.levels[e.item.lv]?.name : '';
    return `${e.item.name} — ${TYPE_LABELS[e.item.cls] ?? e.item.cls.replace(/^Ifc/, '')}${level ? ` · ${level}` : ''}`;
  }
  function showInfo(e: Entry | null, pinned: boolean): void {
    info.hidden = !e;
    info.textContent = e ? describe(e) : '';
    info.dataset.pinned = pinned ? 'true' : 'false';
  }
  function setHover(e: Entry | null): void {
    if (e === hovered) return;
    if (hovered !== picked) setEmissive(hovered, false);
    hovered = e;
    if (e) setEmissive(e, true);
    if (!picked) showInfo(e, false);
    canvas.style.cursor = e ? 'pointer' : 'grab';
    dirty = true;
  }
  function pick(e: Entry | null): void {
    if (picked && picked !== e) setEmissive(picked, false);
    picked = e;
    if (e) { setEmissive(e, true); showInfo(e, true); } else showInfo(hovered, false);
    dirty = true;
  }
  function hit(ev: PointerEvent | MouseEvent): { entry: Entry; point: Vector3 } | null {
    const rect = canvas.getBoundingClientRect();
    pointer.set(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const meshes: Mesh[] = [];
    for (const e of entries) if (e.meshes[0]?.visible) meshes.push(...e.meshes);
    const found = raycaster.intersectObjects(meshes, false).find((h) => (h.object as Mesh).visible);
    if (!found) return null;
    const entry = meshOwner.get(found.object as Mesh);
    return entry ? { entry, point: found.point } : null;
  }

  let dragging = false, moved = 0, downAt = { x: 0, y: 0 };
  canvas.addEventListener('pointerdown', (ev) => { dragging = true; moved = 0; downAt = { x: ev.clientX, y: ev.clientY }; canvas.style.cursor = 'grabbing'; });
  canvas.addEventListener('pointermove', (ev) => {
    if (dragging) { moved = Math.max(moved, Math.hypot(ev.clientX - downAt.x, ev.clientY - downAt.y)); return; }
    if (ev.pointerType === 'touch') return;
    setHover(hit(ev)?.entry ?? null);
  });
  const release = (ev: PointerEvent) => {
    const wasClick = dragging && moved < 5;
    dragging = false;
    canvas.style.cursor = hovered ? 'pointer' : 'grab';
    if (wasClick && ev.type === 'pointerup') { const h = hit(ev); pick(h && h.entry !== picked ? h.entry : null); }
  };
  canvas.addEventListener('pointerup', release);
  canvas.addEventListener('pointercancel', () => { dragging = false; });
  canvas.addEventListener('pointerleave', () => { if (!dragging) setHover(null); });
  canvas.addEventListener('dblclick', (ev) => {
    const h = hit(ev);
    if (!h) return;
    const bs = h.entry.bounds.clone().applyMatrix4(model.matrixWorld).getBoundingSphere(new Sphere());
    const d = Math.max(fitDistance(Math.max(bs.radius, 0.6), FOV, aspect, 1.6), 2);
    const dir = camera.position.clone().sub(controls.target).normalize();
    if (projection === 'orthographic') flyTo(bs.center.clone().addScaledVector(dir, radius * 8), bs.center, Math.min(Math.max(orthoHeight(homeDistance(), FOV) / orthoHeight(d, FOV), 0.3), 60));
    else flyTo(bs.center.clone().addScaledVector(dir, d), bs.center);
    pick(h.entry);
  });

  // --- keyboard: the model can be moved without a mouse ----------------------------------------------------------------------------------
  canvas.addEventListener('keydown', (ev) => {
    const step = 0.12;
    const spherical = camera.position.clone().sub(controls.target);
    const key = ev.key;
    const quick = (cb: () => void) => { ev.preventDefault(); cb(); };
    if (key === 'ArrowLeft' || key === 'ArrowRight') quick(() => { spherical.applyAxisAngle(new Vector3(0, 1, 0), key === 'ArrowLeft' ? step : -step); camera.position.copy(controls.target).add(spherical); controls.update(); dirty = true; });
    else if (key === 'ArrowUp' || key === 'ArrowDown') quick(() => {
      const right = new Vector3().crossVectors(spherical, new Vector3(0, 1, 0)).normalize();
      const turned = spherical.clone().applyAxisAngle(right, key === 'ArrowUp' ? -step : step);
      if (Math.abs(Math.asin(turned.y / turned.length())) < Math.PI / 2 - 0.02) { camera.position.copy(controls.target).add(turned); controls.update(); dirty = true; }
    });
    else if (key === '+' || key === '=' || key === '-' || key === '_') quick(() => {
      const f = key === '+' || key === '=' ? 0.85 : 1.18;
      if (camera === perspective) camera.position.copy(controls.target).addScaledVector(spherical, f); else { orthographic.zoom = Math.min(Math.max(orthographic.zoom / f, 0.05), 80); orthographic.updateProjectionMatrix(); }
      controls.update(); dirty = true;
    });
    else if (key === 'Home' || key === '0') quick(() => setView('perspective'));
    else if (/^[1-6]$/.test(key)) quick(() => setView(VIEWS[Number(key) - 1].id));
    else if (key === 'p' || key === 'P') quick(() => setProjection(projection === 'perspective' ? 'orthographic' : 'perspective'));
    else if (key === 'Escape') quick(() => pick(null));
  });

  // --- the panel ----------------------------------------------------------------------------------------------------------------------------
  const viewButtons = new Map<string, HTMLButtonElement>();
  function markViews(): void { for (const [id, b] of viewButtons) b.setAttribute('aria-pressed', String(id === viewName)); }
  const projButtons = { perspective: $<HTMLButtonElement>('proj-perspective'), orthographic: $<HTMLButtonElement>('proj-orthographic') };
  function markProjection(): void { for (const [k, b] of Object.entries(projButtons)) b.setAttribute('aria-pressed', String(k === projection)); }

  const viewsBox = $('views');
  for (const v of VIEWS) {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = v.label; b.dataset.view = v.id; b.setAttribute('aria-pressed', 'false');
    b.addEventListener('click', () => { setView(v.id); canvas.focus({ preventScroll: true }); });
    viewsBox.appendChild(b); viewButtons.set(v.id, b);
  }
  projButtons.perspective.addEventListener('click', () => setProjection('perspective'));
  projButtons.orthographic.addEventListener('click', () => setProjection('orthographic'));

  const floorsBox = $('floors');
  const floorButtons: HTMLButtonElement[] = [];
  const markFloors = () => floorButtons.forEach((b, i) => b.setAttribute('aria-pressed', String((i === 0 ? showing.upTo === null : showing.upTo === i - 1))));
  if (data.levels.length > 1) {
    ['All floors', ...data.levels.map((l) => `Up to ${l.name}`)].forEach((text, i) => {
      const b = document.createElement('button');
      b.type = 'button'; b.textContent = text; b.dataset.floor = String(i - 1);
      b.addEventListener('click', () => { showing.upTo = i === 0 ? null : i - 1; markFloors(); applyVisibility(); });
      floorsBox.appendChild(b); floorButtons.push(b);
    });
    markFloors();
  } else $('floors-section').hidden = true;

  const togglesBox = $('toggles');
  const present = new Set(entries.map((e) => e.item.cat));
  function addToggle(id: string, label: string, checked: boolean, on: (v: boolean) => void): void {
    const wrap = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'checkbox'; input.checked = checked; input.dataset.toggle = id;
    input.addEventListener('change', () => on(input.checked));
    wrap.append(input, document.createTextNode(` ${label}`));
    togglesBox.appendChild(wrap);
  }
  const roofBox = new Map<string, HTMLInputElement>();
  const insideBtn = $<HTMLButtonElement>('btn-inside');
  const markInside = () => insideBtn.setAttribute('aria-pressed', String(!showing.categories.has('roof')));
  for (const c of CATEGORIES) if (present.has(c.id)) addToggle(c.id, c.label, true, (v) => { if (v) showing.categories.add(c.id); else showing.categories.delete(c.id); markInside(); applyVisibility(); });
  togglesBox.querySelectorAll<HTMLInputElement>('input').forEach((i) => roofBox.set(i.dataset.toggle ?? '', i));
  if (!present.has('roof')) insideBtn.hidden = true;
  insideBtn.addEventListener('click', () => {
    const goingIn = showing.categories.has('roof');
    if (goingIn) showing.categories.delete('roof'); else showing.categories.add('roof');
    const box = roofBox.get('roof');
    if (box) box.checked = !goingIn;
    markInside();
    applyVisibility();
    if (goingIn) {
      const offset = cameraOffset(homeDistance(), INSIDE.azimuth, INSIDE.elevation);
      if (projection === 'orthographic') sizeOrtho(homeDistance());
      flyTo(new Vector3(centre.x + offset[0], centre.y + offset[1], centre.z + offset[2]), centre, projection === 'orthographic' ? 1 : camera.zoom);
      viewName = 'inside'; markViews();
    } else setView('perspective');
  });
  if (data.rooms.length) addToggle('labels', 'Room names', true, (v) => { withLabels = v; updateLabels(true); });
  addToggle('ground', 'Ground and grid', true, (v) => { withGround = v; applyVisibility(); });

  $('btn-reset').addEventListener('click', () => { pick(null); setView('perspective'); });
  $('btn-full').addEventListener('click', () => { if (document.fullscreenElement) void document.exitFullscreen(); else void document.documentElement.requestFullscreen?.(); });
  $('btn-picture').addEventListener('click', () => {
    renderer.render(scene, camera);
    canvas.toBlob((blob) => {
      if (!blob) return;
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${data.title.replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'model'}-v${data.version}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    });
  });
  const help = $('help');
  $('btn-help').addEventListener('click', () => { help.hidden = !help.hidden; $('btn-help').setAttribute('aria-expanded', String(!help.hidden)); });
  $('help-close').addEventListener('click', () => { help.hidden = true; $('btn-help').setAttribute('aria-expanded', 'false'); });
  const panel = $('panel');
  $('btn-options').addEventListener('click', () => { panel.classList.toggle('open'); $('btn-options').setAttribute('aria-expanded', String(panel.classList.contains('open'))); });
  const themeBtn = $('btn-theme');
  const setTheme = (t: 'light' | 'dark') => {
    document.documentElement.dataset.theme = t;
    themeBtn.setAttribute('aria-pressed', String(t === 'dark'));
    (plate.material as MeshStandardMaterial).color.set(t === 'dark' ? 0x1b2029 : 0xe9edf3);
    (grid.material as LineBasicMaterial).color.set(t === 'dark' ? 0x4a5363 : 0xaab3c2);
    dirty = true;
  };
  setTheme(window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  themeBtn.addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));

  $('title').textContent = data.title;
  $('meta').textContent = subtitle(data.version, data.created, data.elements.length);

  // --- the loop ---------------------------------------------------------------------------------------------------------------------------
  makeControls();
  const home = cameraOffset(homeDistance(), VIEWS[0].azimuth, VIEWS[0].elevation);
  camera.position.set(centre.x + home[0], centre.y + home[1], centre.z + home[2]);
  controls.target.copy(centre);
  controls.update();
  markViews(); markProjection(); applyVisibility();
  viewName = 'perspective'; markViews();
  new ResizeObserver(resize).observe(stage);
  resize();

  function frame(now: number): void {
    if (flight) {
      const t = ease((now - flight.start) / flight.ms);
      camera.position.lerpVectors(flight.from.p, flight.to.p, t);
      controls.target.lerpVectors(flight.from.t, flight.to.t, t);
      if (camera === orthographic) { orthographic.zoom = flight.from.z + (flight.to.z - flight.from.z) * t; orthographic.updateProjectionMatrix(); }
      controls.update();                                                              // while the camera flies, the controls' own change event must not say "free"
      if (t >= 1) flight = null;
      dirty = true;
    }
    if (controls.update()) dirty = true;
    if (dirty) {
      camera.updateMatrixWorld();
      renderer.render(scene, camera);
      updateLabels(true);
      dirty = false;
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  $('loading').hidden = true;

  return {
    view: () => ({ name: viewName, projection, position: camera.position.toArray(), target: controls.target.toArray(), distance: distanceNow() }),
    setView, setProjection,
    visibleCount: () => entries.filter((e) => e.meshes[0]?.visible).length,
    totalCount: () => entries.length,
    selected: () => (picked ? picked.item.id : null),
  };
}
