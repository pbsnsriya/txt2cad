import AxeBuilder from '@axe-core/playwright';
import { expect, test as base, type APIRequestContext, type Page } from '@playwright/test';

export const API = `http://127.0.0.1:${process.env.E2E_API_PORT ?? 8771}`;
export const HOUSE = 'Two storey house with a kitchen, living room and three bedrooms, a garage.';
export const CABIN = 'A small one storey cabin with one bedroom and a kitchen.';

type Fixtures = { allowErrors: RegExp[]; failures: string[] };

/** Every test fails on a console error, an uncaught exception or a 5xx. A test that provokes an error on purpose lists it in `allowErrors`. */
export const test = base.extend<Fixtures>({
  allowErrors: [[], { option: true }],
  failures: [async ({ page, allowErrors }, use) => {
    const failures: string[] = [];
    page.on('console', (m) => { if (m.type() === 'error' && !allowErrors.some((r) => r.test(m.text()))) failures.push(`console: ${m.text()}`); });
    page.on('pageerror', (e) => failures.push(`pageerror: ${e.message} | ${(e.stack ?? '').split('\n').slice(1, 6).join(' <- ')}`));
    page.on('response', (r) => { if (r.status() >= 500) failures.push(`HTTP ${r.status()} ${r.url()}`); });
    await use(failures);
    expect(failures, 'console errors, uncaught exceptions or 5xx responses').toEqual([]);
  }, { auto: true }],
});
export { expect };

export async function resetProjects(request: APIRequestContext): Promise<void> {
  for (const p of await (await request.get(`${API}/api/projects`)).json()) await request.delete(`${API}/api/projects/${p.id}`);
}

export const composer = (page: Page) => page.getByLabel('Describe what to build');

/** The list of projects is a sheet opened from the top bar. */
export async function openProjects(page: Page) {
  await page.getByRole('button', { name: 'Projects' }).click();
  const sheet = page.getByRole('dialog', { name: 'Projects' });
  await expect(sheet).toBeVisible();
  return sheet;
}
export async function openProjectByName(page: Page, name: RegExp): Promise<void> {
  const sheet = await openProjects(page);
  await sheet.getByRole('button', { name }).first().click();
}
export async function newProject(page: Page): Promise<void> {
  const sheet = await openProjects(page);
  await sheet.getByRole('button', { name: 'New project' }).click();
}

/** Open the app, send a prompt, wait for the finished version. */
export async function build(page: Page, prompt = HOUSE): Promise<void> {
  await page.goto('/');
  await composer(page).fill(prompt);
  await composer(page).press('Enter');
  await expect(page.getByText(/Version 1:/).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId('viewer').getByText(/v1 · \d+ elements/)).toBeVisible();
  await modelShown(page, 1);
}

/** Wait until the 3D view is showing the saved IFC of this version (not a preview), so clicks and checks never race the final model swap. */
export async function modelShown(page: Page, version: number): Promise<void> {
  await expect(page.locator(`[data-model-url$="/versions/${version}/ifc"]`)).toHaveCount(1, { timeout: 30_000 });
}

export async function projects(request: APIRequestContext): Promise<{ id: string; name: string }[]> {
  return (await request.get(`${API}/api/projects`)).json();
}

/** axe scan limited to the failures that block people: serious and critical, WCAG 2 A and AA. */
export async function expectAccessible(page: Page, label: string, exclude: string[] = []): Promise<void> {
  await page.emulateMedia({ reducedMotion: 'reduce' });          // colour transitions finish at once, so axe never measures a half-faded colour
  await page.waitForTimeout(150);
  let axe = new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']);
  for (const sel of exclude) axe = axe.exclude(sel);
  const { violations } = await axe.analyze();
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  expect(blocking.map((v) => `${v.id} (${v.impact}): ${v.help}  [${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}]`), `accessibility on ${label}`).toEqual([]);
}
