// Copies the web-ifc WebAssembly binary next to the app so the viewer can load it. Runs after npm install.
import { copyFileSync, mkdirSync } from 'node:fs';

mkdirSync('public/wasm', { recursive: true });
copyFileSync('node_modules/web-ifc/web-ifc.wasm', 'public/wasm/web-ifc.wasm');
console.log('web-ifc wasm copied to public/wasm');
