import { build, expect, resetProjects, test } from './helpers';

test.beforeEach(({ request }) => resetProjects(request));

test('F06-H1 the Drawings tab shows the plans of every level', async ({ page }) => {
  await build(page);
  await page.getByRole('tab', { name: 'Drawings' }).click();
  const img = page.getByRole('img', { name: /Floor plans/ });
  await expect(img).toBeVisible();
  await expect.poll(() => img.evaluate((i: HTMLImageElement) => i.complete && i.naturalWidth > 100)).toBe(true);
  await expect(page.getByRole('tabpanel', { name: 'Drawings' }).getByRole('button', { name: 'DXF' })).toBeVisible();
});

test('F06-H2 the design check is honest about itself and "Show in model" goes back to the 3D view', async ({ page }) => {
  await build(page);
  await page.getByRole('tab', { name: 'Design check' }).click();
  await expect(page.getByText(/Indicative only/)).toBeVisible();
  await expect(page.getByText('IRC R311.1')).toBeVisible();
  await expect(page.getByText(/Not modelled, so not checked/)).toBeVisible();
  await page.getByRole('button', { name: 'Show in model' }).first().click();
  await expect(page.getByTestId('viewer')).toBeVisible();
  await expect(page.locator('canvas')).toHaveCount(1);
});

test('F06-H3 quantities carry no prices until the user types one', async ({ page }) => {
  await build(page);
  await page.getByRole('tab', { name: 'Quantities' }).click();
  await expect(page.getByText(/Prices are not included/)).toBeVisible();
  const rate = page.getByLabel(/Rate per m2 for External wall/);
  await rate.fill('');
  await rate.fill('1500');
  await expect(page.getByText(/Total of the rows you priced/).locator('..')).toContainText(/\d{3}/);
  await page.reload();                                           // the rate is remembered on this computer
  await page.getByRole('navigation', { name: 'Sessions' }).getByRole('button', { name: /Two storey house/ }).first().click();
  await page.getByRole('tab', { name: 'Quantities' }).click();
  await expect(page.getByLabel(/Rate per m2 for External wall/)).toHaveValue('1500');
  await page.getByLabel(/Rate per m2 for External wall/).fill('');
});

test('F06-E1 Home has no analysis tabs; they appear with a version', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('tab', { name: 'Drawings' })).toHaveCount(0);
  await build(page);
  await expect(page.getByRole('tab', { name: 'Drawings' })).toBeEnabled();
});

test('F06-E2 switching tabs back and forth keeps the same 3D viewer alive', async ({ page }) => {
  await build(page);
  await page.locator('canvas').evaluate((c) => { (c as HTMLCanvasElement).dataset.marker = 'same'; });
  for (const tab of ['Drawings', 'Design check', 'Quantities', '3D model']) await page.getByRole('tab', { name: tab }).click();
  await expect(page.locator('canvas[data-marker="same"]')).toHaveCount(1);
});
