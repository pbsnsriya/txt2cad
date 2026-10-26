import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import type { BrowserContext, Page } from '@playwright/test';
import { build, expect, resetProjects, test } from './helpers';

test.beforeEach(({ request }) => resetProjects(request));

const HOUSE = 'Two storey house with a kitchen, living room and three bedrooms, a garage. Gable roof. Furnish every room.';

type Handle = { view(): { name: string; projection: string; position: number[]; target: number[]; distance: number }; visibleCount(): number; totalCount(): number; selected(): string | null };
const share = (page: Page) => page.evaluate(() => {
  const s = (window as unknown as { txt2cadShare: Handle }).txt2cadShare;
  return { view: s.view(), visible: s.visibleCount(), total: s.totalCount(), selected: s.selected() };
});

/** Export the shareable page from the app and open the saved file from disk, like a person who was sent it. */
async function exported(page: Page, context: BrowserContext): Promise<{ file: string; opened: Page; requests: string[]; errors: string[] }> {
  await build(page, HOUSE);
  await page.getByRole('button', { name: 'Export' }).click();
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('menuitem', { name: /Shareable page/ }).click()]);
  expect(download.suggestedFilename()).toMatch(/-v1\.html$/);
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'txt2cad-share-')), download.suggestedFilename());
  await download.saveAs(file);
  const opened = await context.newPage();
  const requests: string[] = [], errors: string[] = [];
  opened.on('request', (r) => requests.push(r.url()));
  opened.on('pageerror', (e) => errors.push(e.message));
  opened.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await opened.setViewportSize({ width: 1280, height: 800 });
  await opened.goto(`file:///${file.replace(/\\/g, '/')}`);
  await expect(opened.locator('#loading')).toBeHidden({ timeout: 30_000 });
  await opened.waitForFunction(() => Boolean((window as unknown as { txt2cadShare?: unknown }).txt2cadShare));
  return { file, opened, requests, errors };
}

test('F21-H1 the shareable page opens offline from a file and shows the model', async ({ page, context }) => {
  const { file, opened, requests, errors } = await exported(page, context);
  expect(fs.statSync(file).size).toBeGreaterThan(300_000);
  expect(fs.statSync(file).size).toBeLessThan(2_000_000);
  await expect(opened.getByRole('heading', { level: 1 })).toContainText(/House|two storey/i);
  await expect(opened.locator('#meta')).toContainText('Version 1');
  const state = await share(opened);
  expect(state.total).toBeGreaterThan(40);
  expect(state.visible).toBe(state.total);
  expect(state.view.projection).toBe('perspective');
  // nothing was asked of the network: only the file itself
  expect(requests.filter((u) => !/^(file|blob|data):/.test(u)), 'requests that left the file').toEqual([]);
  const csp = await opened.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute('content');
  expect(csp).toContain("connect-src 'none'");
  expect(errors.filter((e) => !/GPU stall|ReadPixels|Context/i.test(e))).toEqual([]);
  // something is really drawn: the saved picture holds only the model, so it is large with the model shown and almost empty with everything switched off
  const picture = async () => {
    const [d] = await Promise.all([opened.waitForEvent('download'), opened.getByRole('button', { name: 'Save picture' }).click()]);
    const out = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'txt2cad-pic-')), d.suggestedFilename());
    await d.saveAs(out);
    return fs.statSync(out).size;
  };
  const withModel = await picture();
  for (const name of ['Walls', 'Floors', 'Roof', 'Doors and windows', 'Stairs', 'Furniture and lights', 'Floor and wall finishes', 'Ground and grid']) {
    const box = opened.getByRole('checkbox', { name });
    if (await box.count()) await box.uncheck();
  }
  expect((await share(opened)).visible).toBe(0);
  const without = await picture();
  expect(withModel).toBeGreaterThan(8_000);
  expect(without).toBeLessThan(withModel / 4);
});

test('F21-H2 the camera can be moved: drag, wheel, keys, views and the two projections', async ({ page, context }) => {
  const { opened } = await exported(page, context);
  const canvas = opened.locator('#scene');
  const box = (await canvas.boundingBox())!;
  const mid = { x: box.x + box.width / 2 - 120, y: box.y + box.height / 2 };
  const first = await share(opened);

  await opened.mouse.move(mid.x, mid.y);                                                   // drag turns it
  await opened.mouse.down();
  await opened.mouse.move(mid.x + 160, mid.y + 40, { steps: 8 });
  await opened.mouse.up();
  const turned = await share(opened);
  expect(turned.view.name).toBe('free');
  expect(turned.view.position).not.toEqual(first.view.position);
  expect(turned.view.distance).toBeCloseTo(first.view.distance, 0);                         // turning does not zoom

  await opened.mouse.move(mid.x, mid.y);                                                   // the wheel zooms
  await opened.mouse.wheel(0, -500);
  await opened.waitForTimeout(500);
  expect((await share(opened)).view.distance).toBeLessThan(turned.view.distance - 1);

  await opened.mouse.move(mid.x, mid.y);                                                   // right button moves it sideways
  const before = (await share(opened)).view.target;
  await opened.mouse.down({ button: 'right' });
  await opened.mouse.move(mid.x + 120, mid.y, { steps: 6 });
  await opened.mouse.up({ button: 'right' });
  expect((await share(opened)).view.target).not.toEqual(before);

  await opened.getByRole('button', { name: 'Top', exact: true }).click();                  // a named view
  await expect.poll(async () => (await share(opened)).view.name).toBe('top');
  await expect.poll(async () => { const v = (await share(opened)).view; return v.position[1] - v.target[1] > Math.hypot(v.position[0] - v.target[0], v.position[2] - v.target[2]) * 10; }).toBe(true);   // straight above
  await expect(opened.getByRole('button', { name: 'Top', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await opened.getByRole('button', { name: 'East', exact: true }).click();
  await expect.poll(async () => (await share(opened)).view.name).toBe('right');
  await expect.poll(async () => { const v = (await share(opened)).view; return v.position[0] - v.target[0] > 10 && Math.abs(v.position[1] - v.target[1]) < 1; }).toBe(true);     // the camera stands east of the model, level, looking west

  await opened.getByRole('button', { name: 'Orthographic' }).click();                      // orthographic and back
  await expect.poll(async () => (await share(opened)).view.projection).toBe('orthographic');
  await expect(opened.getByRole('button', { name: 'Orthographic' })).toHaveAttribute('aria-pressed', 'true');
  await opened.getByRole('button', { name: 'South', exact: true }).click();
  await expect.poll(async () => (await share(opened)).view.name).toBe('front');
  await opened.getByRole('button', { name: 'Perspective', exact: true }).click();
  await expect.poll(async () => (await share(opened)).view.projection).toBe('perspective');

  await canvas.focus();                                                                    // the keyboard works too
  await opened.keyboard.press('2');
  await expect.poll(async () => (await share(opened)).view.name).toBe('top');
  await opened.keyboard.press('Home');
  await expect.poll(async () => (await share(opened)).view.name).toBe('perspective');
  const beforeKey = (await share(opened)).view.position;
  await opened.keyboard.press('ArrowLeft');
  expect((await share(opened)).view.position).not.toEqual(beforeKey);
  await opened.keyboard.press('p');
  await expect.poll(async () => (await share(opened)).view.projection).toBe('orthographic');
  await opened.getByRole('button', { name: 'Reset view' }).click();
  await expect.poll(async () => (await share(opened)).view.name).toBe('perspective');
});

test('F21-H3 floors and layers can be switched, and room names show only for rooms that can be seen', async ({ page, context }) => {
  const { opened } = await exported(page, context);
  const total = (await share(opened)).total;
  const labels = opened.locator('.label:not([hidden])');
  await expect(labels).toHaveCount(0);                                                       // the roof and walls hide every room from outside

  await opened.getByRole('checkbox', { name: 'Roof' }).uncheck();
  await opened.getByRole('button', { name: 'Top', exact: true }).click();
  await expect.poll(async () => (await share(opened)).view.name).toBe('top');
  await expect.poll(() => labels.count()).toBeGreaterThan(2);                                // with the roof off, looking down, rooms show their names
  expect((await share(opened)).visible).toBeLessThan(total);

  await opened.getByRole('button', { name: 'Up to Ground floor' }).click();
  const ground = await share(opened);
  expect(ground.visible).toBeLessThan(total - 5);
  await expect(opened.getByRole('button', { name: 'Up to Ground floor' })).toHaveAttribute('aria-pressed', 'true');
  await opened.getByRole('button', { name: 'All floors' }).click();
  await opened.getByRole('checkbox', { name: 'Roof' }).check();
  expect((await share(opened)).visible).toBe(total);

  await opened.getByRole('checkbox', { name: 'Furniture and lights' }).uncheck();
  expect((await share(opened)).visible).toBeLessThan(total - 10);
  await opened.getByRole('checkbox', { name: 'Furniture and lights' }).check();
  await opened.getByRole('checkbox', { name: 'Ground and grid' }).uncheck();
  await opened.getByRole('checkbox', { name: 'Ground and grid' }).check();
});

test('F21-H4 an element can be inspected, flown to, and the picture saved', async ({ page, context }) => {
  const { opened } = await exported(page, context);
  const canvas = opened.locator('#scene');
  const box = (await canvas.boundingBox())!;
  const point = { x: box.x + box.width / 2 - 140, y: box.y + box.height / 2 + 60 };
  await opened.mouse.move(point.x, point.y);
  await expect(opened.locator('#info')).toBeVisible();                                      // hovering says what is under the pointer
  await expect(opened.locator('#info')).toContainText(/Wall|Window|Door|Roof|Floor|Stair|Light|Furniture|Finish/);
  await opened.mouse.click(point.x, point.y);
  await expect.poll(async () => (await share(opened)).selected).not.toBeNull();
  await expect(opened.locator('#info')).toHaveAttribute('data-pinned', 'true');
  const far = (await share(opened)).view.distance;
  await opened.mouse.dblclick(point.x, point.y);
  await expect.poll(async () => (await share(opened)).view.distance, { timeout: 5000 }).toBeLessThan(far * 0.8);
  await canvas.focus();
  await opened.keyboard.press('Escape');
  await expect.poll(async () => (await share(opened)).selected).toBeNull();

  const [picture] = await Promise.all([opened.waitForEvent('download'), opened.getByRole('button', { name: 'Save picture' }).click()]);
  expect(picture.suggestedFilename()).toMatch(/-v1\.png$/);
  const saved = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'txt2cad-pic-')), picture.suggestedFilename());
  await picture.saveAs(saved);
  const bytes = fs.readFileSync(saved);
  expect(bytes.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');                  // a real PNG
  expect(bytes.length).toBeGreaterThan(5000);
});

test('F21-H5 help, dark theme and a phone screen', async ({ page, context }) => {
  const { opened } = await exported(page, context);
  await opened.getByRole('button', { name: 'Controls' }).click();
  await expect(opened.getByRole('dialog')).toContainText('Moving around the model');
  await opened.getByRole('button', { name: 'Close' }).click();
  await expect(opened.getByRole('dialog')).toBeHidden();
  await opened.getByRole('button', { name: 'Dark' }).click();
  await expect(opened.locator('html')).toHaveAttribute('data-theme', 'dark');
  await opened.getByRole('button', { name: 'Dark' }).click();
  await expect(opened.locator('html')).toHaveAttribute('data-theme', 'light');

  await opened.setViewportSize({ width: 390, height: 800 });                                // a phone: the options sit behind a button
  await expect(opened.getByRole('button', { name: 'Options' })).toBeVisible();
  await expect(opened.locator('#panel')).toBeHidden();
  await opened.getByRole('button', { name: 'Options' }).click();
  await expect(opened.locator('#panel')).toBeVisible();
  const overflow = await opened.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test('F21-E1 the page passes an automatic accessibility check, and a file with no model says so', async ({ page, context }) => {
  const { file, opened } = await exported(page, context);
  const result = await new AxeBuilder({ page: opened }).withTags(['wcag2a', 'wcag2aa']).analyze();
  expect(result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)).toEqual([]);

  const broken = path.join(path.dirname(file), 'broken.html');                              // the same page with its data cut out
  fs.writeFileSync(broken, fs.readFileSync(file, 'utf8').replace(/(<script type="text\/plain" id="model-data">)[^<]*/, '$1not-a-model'));
  const bad = await context.newPage();
  await bad.goto(`file:///${broken.replace(/\\/g, '/')}`);
  await expect(bad.locator('#loading')).toContainText(/could not be shown|not in a format/);
  await expect(bad.locator('#loading')).toHaveAttribute('role', 'alert');
});

test('F21-H6 "Look inside" takes the roof off, tilts the camera down and shows the room names; pressed again it puts it all back', async ({ page, context }) => {
  const { opened } = await exported(page, context);
  const labels = opened.locator('.label:not([hidden])');
  const total = (await share(opened)).total;
  await expect(labels).toHaveCount(0);
  await opened.getByRole('button', { name: 'Look inside' }).click();
  await expect(opened.getByRole('button', { name: 'Look inside' })).toHaveAttribute('aria-pressed', 'true');
  await expect(opened.getByRole('checkbox', { name: 'Roof' })).not.toBeChecked();
  await expect.poll(async () => (await share(opened)).view.name).toBe('inside');
  await expect.poll(() => labels.count(), { timeout: 8000 }).toBeGreaterThan(3);
  expect((await share(opened)).visible).toBeLessThan(total);
  await opened.getByRole('button', { name: 'Look inside' }).click();
  await expect(opened.getByRole('checkbox', { name: 'Roof' })).toBeChecked();
  await expect.poll(async () => (await share(opened)).view.name).toBe('perspective');
  expect((await share(opened)).visible).toBe(total);
  await expect(labels).toHaveCount(0);
});
