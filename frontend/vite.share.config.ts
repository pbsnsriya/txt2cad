import { defineConfig } from 'vite';

/** Builds the viewer that goes inside every shareable page: one script and one stylesheet, which the backend puts into the HTML file. Run `npm run build:share` after changing src/share. */
export default defineConfig({
  publicDir: false,
  build: {
    lib: { entry: 'src/share/main.ts', formats: ['iife'], name: 'Txt2cadShare', fileName: () => 'share-viewer.js', cssFileName: 'share-viewer' },
    outDir: '../backend/app/export/assets',
    emptyOutDir: false,
    minify: true,
    target: 'es2020',
    cssCodeSplit: false,
    reportCompressedSize: true,
  },
});
