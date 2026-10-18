import type { Page } from '@playwright/test';
import { build, composer, expect, resetProjects, test } from './helpers';

test.beforeEach(({ request }) => resetProjects(request));

/** Click around the middle of the model until something is selected. The first clicks after a load can miss while the 3D tiles are still streaming in. */
async function clickModel(page: Page): Promise<void> {
  const box = (await page.getByTestId('viewer').boundingBox())!;
  const spots = [[0.45, 0.55], [0.5, 0.45], [0.4, 0.65], [0.55, 0.6], [0.6, 0.5], [0.35, 0.55]];
  for (let i = 0; i < 16; i++) {
    const [fx, fy] = spots[i % spots.length];
    await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
    await page.waitForTimeout(700);
    if (await page.getByTestId('selection').count()) return;
  }
}

test('F03-H1 clicking selects an element and says what the next message is about', async ({ page }) => {
  await build(page);
  await clickModel(page);
  await expect(page.getByTestId('selection')).toBeVisible();
  await expect(page.getByTestId('context-chip')).toContainText('Re:');
});

test('F03-H2 the next message carries the element id', async ({ page }) => {
  await build(page);
  await clickModel(page);
  await expect(page.getByTestId('selection')).toBeVisible();
  const sent = page.waitForRequest((r) => r.method() === 'POST' && r.url().endsWith('/runs'));
  await composer(page).fill('make this bigger');
  await composer(page).press('Enter');
  const body = (await sent).postDataJSON();
  expect(body.focus_guids).toHaveLength(1);
  expect(body.focus_guids[0]).toMatch(/^[0-9A-Za-z_$]{22}$/);
  await expect(page.getByTestId('run-tags')).toContainText('About:');          // the request shows what it was about
});

test('F03-E1 dragging to orbit selects nothing', async ({ page }) => {
  await build(page);
  const box = (await page.getByTestId('viewer').boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.55);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.5, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(800);
  await expect(page.getByTestId('selection')).toHaveCount(0);
});

test('F03-E2 clearing the selection removes the highlight note and the chip', async ({ page }) => {
  await build(page);
  await clickModel(page);
  await expect(page.getByTestId('selection')).toBeVisible();
  await page.getByRole('button', { name: 'Unpick' }).first().click();
  await expect(page.getByTestId('selection')).toHaveCount(0);
  await expect(page.getByTestId('context-chip')).toHaveCount(0);
});


/** Shift-click around the model until `n` different parts are tagged. */
async function addUntil(page: Page, n: number): Promise<void> {
  const box = (await page.getByTestId('viewer').boundingBox())!;
  const spots = [[0.3, 0.6], [0.7, 0.55], [0.5, 0.7], [0.62, 0.42], [0.4, 0.5], [0.55, 0.62], [0.25, 0.5], [0.75, 0.65]];
  for (let i = 0; i < 24 && (await page.getByTestId('tag').count()) < n; i++) {
    const [fx, fy] = spots[i % spots.length];
    await page.keyboard.down('Shift');
    await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
    await page.keyboard.up('Shift');
    await page.waitForTimeout(600);
  }
}

test('F03-H3 shift-click adds more parts; each is a tag in the chat and all go with the message', async ({ page }) => {
  await build(page);
  await clickModel(page);
  await expect(page.getByTestId('tag')).toHaveCount(1);
  await addUntil(page, 2);
  const tags = await page.getByTestId('tag').count();
  expect(tags).toBeGreaterThanOrEqual(2);
  await expect(page.getByTestId('selection')).toContainText(`${tags} selected`);
  const sent = page.waitForRequest((r) => r.method() === 'POST' && r.url().endsWith('/runs'));
  await composer(page).fill('make these bigger');
  await composer(page).press('Enter');
  const body = (await sent).postDataJSON();
  expect(body.focus_guids).toHaveLength(tags);
  expect(new Set(body.focus_guids).size).toBe(tags);
});

test('F03-H4 closing one tag takes just that part out of the selection', async ({ page }) => {
  await build(page);
  await clickModel(page);
  await addUntil(page, 2);
  const before = await page.getByTestId('tag').count();
  expect(before).toBeGreaterThanOrEqual(2);
  await page.getByTestId('tag').first().getByRole('button').click();
  await expect(page.getByTestId('tag')).toHaveCount(before - 1);
  await page.getByTestId('selection').getByRole('button').click();               // Unpick, or Unpick all
  await expect(page.getByTestId('tag')).toHaveCount(0);
});

test('F03-H5 select area: dragging a box picks everything it touches', async ({ page }) => {
  await build(page);
  const toggle = page.getByRole('button', { name: 'Select area' });
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  const box = (await page.getByTestId('viewer').boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.2, box.y + box.height * 0.2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5, { steps: 6 });
  await expect(page.getByTestId('area-box')).toBeVisible();                      // the box is drawn while dragging
  await page.mouse.move(box.x + box.width * 0.8, box.y + box.height * 0.8, { steps: 6 });
  await page.mouse.up();
  await expect(page.getByTestId('area-box')).toHaveCount(0);
  await expect.poll(() => page.getByTestId('tag').count(), { timeout: 15_000 }).toBeGreaterThanOrEqual(3);
  await expect(page.getByTestId('selection')).toContainText('selected');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
});

test('F03-E3 a click in area mode picks nothing and leaves the camera alone', async ({ page }) => {
  await build(page);
  await page.getByRole('button', { name: 'Select area' }).click();
  const box = (await page.getByTestId('viewer').boundingBox())!;
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.55);
  await page.waitForTimeout(600);
  await expect(page.getByTestId('tag')).toHaveCount(0);
});
