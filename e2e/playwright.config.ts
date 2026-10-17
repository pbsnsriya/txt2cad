import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const live = process.env.E2E_LIVE === '1';
const python = process.env.E2E_PYTHON ?? 'python';

export const API_PORT = Number(process.env.E2E_API_PORT ?? 8771);       // not the dev ports, so the tests never touch real data; set these if something else holds them
export const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5175);

export default defineConfig({
  testDir: './tests',
  timeout: live ? 240_000 : process.env.E2E_VIDEO === '1' ? 120_000 : 60_000,      // finishing a video can take a while
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,                        // one shared backend and database
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  testIgnore: live ? undefined : /live\.spec\.ts/,
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: process.env.E2E_VIDEO === '1' ? { mode: 'on', size: { width: 1440, height: 900 } } : 'off',      // E2E_VIDEO=1 records every test to test-results/ so a good run can be shown
    // Uses the Edge that ships with Windows, so no browser download is needed. On CI set E2E_CHANNEL=chromium after `npx playwright install chromium`.
    channel: process.env.E2E_CHANNEL === 'chromium' ? undefined : (process.env.E2E_CHANNEL ?? 'msedge'),
    launchOptions: { args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] },
  },
  webServer: [
    {
      command: `"${python}" -m app.main`,
      cwd: path.join(here, '..', 'backend'),
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        TXT2CAD_PORT: String(API_PORT),
        TXT2CAD_DATA_DIR: path.join(here, '.data'),
        TXT2CAD_ORIGINS: `http://127.0.0.1:${WEB_PORT},http://localhost:${WEB_PORT}`,
        ...(live ? {} : { GEMINI_API_KEY: '' }),      // offline runs must never reach a real model
      },
    },
    {
      command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
      cwd: path.join(here, '..', 'frontend'),
      url: `http://127.0.0.1:${WEB_PORT}`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: { VITE_API: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
