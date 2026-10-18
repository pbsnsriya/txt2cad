// Copies the files the 3D viewer would otherwise fetch from a public CDN at run time, so nothing is requested from outside this computer:
// the web-ifc WebAssembly binary and the That Open fragments worker. Runs after npm install.
import { copyFileSync, mkdirSync } from 'node:fs';

mkdirSync('public/wasm', { recursive: true });
copyFileSync('node_modules/web-ifc/web-ifc.wasm', 'public/wasm/web-ifc.wasm');
console.log('web-ifc wasm copied to public/wasm');

mkdirSync('public/vendor', { recursive: true });
copyFileSync('node_modules/@thatopen/fragments/dist/Worker/worker.min.mjs', 'public/vendor/fragments-worker.mjs');
console.log('fragments worker copied to public/vendor');
