import type { Category } from './logic';

/** The model as the exported page carries it: gzip, then base64, of this JSON. Positions and indices are base64 of float32 and uint32 arrays. */
export interface Part { c: [number, number, number]; o: number; p: string; i: string }
export interface Item { id: string; cls: string; cat: Category; name: string; lv: number; parts: Part[] }
export interface RoomLabel { name: string; lv: number; c: [number, number, number] }
export interface ModelData {
  v: 1;
  title: string;
  version: number;
  created: string;
  summary: string;
  app: string;
  levels: { id: string; name: string; z: number }[];
  elements: Item[];
  rooms: RoomLabel[];
}

export function fromBase64(text: string): Uint8Array {
  const bin = atob(text.replace(/\s+/g, ''));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function floats(b64: string): Float32Array {
  const bytes = fromBase64(b64);
  return new Float32Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 4);
}

export function uints(b64: string): Uint32Array {
  const bytes = fromBase64(b64);
  return new Uint32Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 4);
}

export class UnsupportedBrowser extends Error {}

/** Unpack the page's data. Needs DecompressionStream, which every current browser has; older ones get a plain message. */
export async function loadModel(b64: string): Promise<ModelData> {
  if (typeof DecompressionStream === 'undefined') throw new UnsupportedBrowser('This browser is too old to open the model. Please use a recent Chrome, Edge, Firefox or Safari.');
  const bytes = fromBase64(b64);
  const stream = new Blob([bytes as BlobPart]).stream().pipeThrough(new DecompressionStream('gzip'));
  const data = JSON.parse(await new Response(stream).text()) as ModelData;
  if (data.v !== 1 || !Array.isArray(data.elements)) throw new Error('The model in this file is not in a format this page understands.');
  return data;
}
