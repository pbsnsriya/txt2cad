/** The parts of the shareable viewer that need no browser: camera placement, framing and what is visible. Tested on their own. */

export type Category = 'wall' | 'floor' | 'roof' | 'opening' | 'stair' | 'furniture' | 'finish' | 'other';

export const CATEGORIES: { id: Category; label: string }[] = [
  { id: 'wall', label: 'Walls' },
  { id: 'floor', label: 'Floors' },
  { id: 'roof', label: 'Roof' },
  { id: 'opening', label: 'Doors and windows' },
  { id: 'stair', label: 'Stairs' },
  { id: 'furniture', label: 'Furniture and lights' },
  { id: 'finish', label: 'Floor and wall finishes' },
];

export const TYPE_LABELS: Record<string, string> = {
  IfcWall: 'Wall', IfcSlab: 'Floor slab', IfcRoof: 'Roof', IfcDoor: 'Door', IfcWindow: 'Window', IfcStair: 'Stair', IfcFurniture: 'Furniture',
  IfcLightFixture: 'Light', IfcCovering: 'Finish', IfcSpace: 'Room', IfcBuildingElementProxy: 'Element',
};

/** Named views: azimuth is degrees round the model from the south (0), going east (90); elevation is degrees above the ground. */
export interface ViewPreset { id: string; label: string; azimuth: number; elevation: number }
export const VIEWS: ViewPreset[] = [
  { id: 'perspective', label: '3D view', azimuth: 35, elevation: 28 },
  { id: 'top', label: 'Top', azimuth: 0, elevation: 89.5 },
  { id: 'front', label: 'South', azimuth: 0, elevation: 0 },
  { id: 'right', label: 'East', azimuth: 90, elevation: 0 },
  { id: 'back', label: 'North', azimuth: 180, elevation: 0 },
  { id: 'left', label: 'West', azimuth: 270, elevation: 0 },
];

/** The view "Look inside" flies to: from above and a little to the south-east, so the rooms of a house without its roof can be read. */
export const INSIDE: ViewPreset = { id: 'inside', label: 'Look inside', azimuth: 25, elevation: 58 };

export function viewById(id: string): ViewPreset {
  if (id === INSIDE.id) return INSIDE;
  return VIEWS.find((v) => v.id === id) ?? VIEWS[0];
}

const rad = (deg: number) => (deg * Math.PI) / 180;

/** Where the camera stands (y up, as three.js has it) for a target, a distance and a view. At azimuth 0 it is south of the target, so north is up in the top view. */
export function cameraOffset(distance: number, azimuthDeg: number, elevationDeg: number): [number, number, number] {
  const a = rad(azimuthDeg), e = rad(elevationDeg);
  return [distance * Math.cos(e) * Math.sin(a), distance * Math.sin(e), distance * Math.cos(e) * Math.cos(a)];
}

/** How far away the camera must be for a sphere of this radius to fit the view, with some air around it. */
export function fitDistance(radius: number, fovDeg: number, aspect: number, margin = 1.18): number {
  const vertical = rad(fovDeg) / 2;
  const horizontal = Math.atan(Math.tan(vertical) * Math.max(aspect, 0.2));
  return (radius * margin) / Math.sin(Math.min(vertical, horizontal));
}

/** The height of the view of an orthographic camera that shows what a perspective camera at this distance shows at the target. */
export function orthoHeight(distance: number, fovDeg: number): number {
  return 2 * distance * Math.tan(rad(fovDeg) / 2);
}

export function ease(t: number): number {
  const x = Math.min(Math.max(t, 0), 1);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
}

export interface Showing { upTo: number | null; categories: Set<Category> }

/** Is an element shown? `upTo` is the highest level index shown (null: all). An element on no level is shown whatever the level. */
export function isShown(el: { cat: Category; lv: number }, s: Showing): boolean {
  if (el.cat !== 'other' && !s.categories.has(el.cat)) return false;
  return s.upTo === null || el.lv < 0 || el.lv <= s.upTo;
}

export function roomShown(room: { lv: number }, s: Showing): boolean {
  return s.upTo === null || room.lv < 0 || room.lv <= s.upTo;
}

/** The text under the title: version, date and what is in the model. */
export function subtitle(version: number, dateIso: string, elements: number): string {
  const d = new Date(dateIso);
  const day = Number.isNaN(d.getTime()) ? '' : ` · ${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`;
  return `Version ${version}${day} · ${elements} elements`;
}
