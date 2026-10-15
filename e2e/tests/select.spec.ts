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
  await expect(page.getByTestId('context-chip')).toContainText('About:');
});

test('F03-H2 the next message carries the element id', async ({ page }) => {
  await build(page);
  await clickModel(page);
  await expect(page.getByTestId('selection')).toBeVisible();
  const sent = page.waitForRequest((r) => r.method() === 'POST' && r.url().endsWith('/runs'));
  await composer(page).fill('make this bigger');
  await composer(page).press('Enter');
  const body = (await sent).postDataJSON();
  expect(body.focus_guid).toMatch(/^[0-9A-Za-z_$]{22}$/);
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
  await page.getByRole('button', { name: 'Clear selection' }).first().click();
  await expect(page.getByTestId('selection')).toHaveCount(0);
  await expect(page.getByTestId('context-chip')).toHaveCount(0);
});
