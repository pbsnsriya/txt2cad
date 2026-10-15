import { build, CABIN, composer, expect, modelShown, projects, resetProjects, test } from './helpers';

test.beforeEach(({ request }) => resetProjects(request));

test('F07-H1 new session, reopening from the list and reloading all land on the right model', async ({ page }) => {
  await build(page, CABIN);
  await page.getByRole('button', { name: 'New session' }).click();
  await expect(page.getByRole('heading', { name: 'What are we building today?' })).toBeVisible();
  await page.getByRole('navigation', { name: 'Sessions' }).getByRole('button', { name: /cabin/i }).first().click();
  await expect(page.getByText(/Version 1:/).first()).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('viewer').getByText(/v1 · \d+ elements/)).toBeVisible({ timeout: 20_000 });
});

test('F07-H2 deleting asks first, focuses the safe button, and Escape backs out', async ({ page, request }) => {
  await build(page, CABIN);
  const del = page.getByRole('button', { name: /Delete session/ });
  await del.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  expect(await projects(request)).toHaveLength(1);
  await del.click();
  await page.getByRole('dialog').getByRole('button', { name: 'Delete session' }).click();
  await expect.poll(async () => (await projects(request)).length).toBe(0);
  await expect(page.getByText('Nothing yet. Describe a building to start.')).toBeVisible();
});

test('F07-E1 the Home screen lists earlier sessions and opens one', async ({ page }) => {
  await build(page, CABIN);
  await page.getByRole('button', { name: 'New session' }).click();
  await page.getByRole('region', { name: 'Recent sessions' }).getByRole('button').first().click();
  await modelShown(page, 1);
  await expect(page.getByText(/Version 1:/).first()).toBeVisible();
  await expect(composer(page)).toBeVisible();
});
