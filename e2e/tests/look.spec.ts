import { build, expect, expectAccessible, openProjects, resetProjects, test } from './helpers';

test.beforeEach(({ request }) => resetProjects(request));

test('F08-H1 the theme choice survives a reload', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('button', { name: 'Switch to light theme' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('F08-E1 accessibility: Home, in both themes', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Start with a sentence' })).toBeVisible();
  await expectAccessible(page, 'Home (light)');
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await expectAccessible(page, 'Home (dark)');
  await page.getByRole('button', { name: 'Switch to light theme' }).click();
});

test('F08-E1 accessibility: workspace, every tab, the export menu and the delete dialog', async ({ page }) => {
  await build(page);
  await expectAccessible(page, 'workspace 3D');
  for (const tab of ['Plans', 'Design check', 'Quantities']) {
    await page.getByRole('tab', { name: tab }).click();
    await expectAccessible(page, `tab ${tab}`);
  }
  await page.getByRole('tab', { name: '3D view' }).click();
  await page.getByRole('button', { name: 'Export' }).click();
  await expectAccessible(page, 'export menu');
  await page.keyboard.press('Escape');
  await openProjects(page).then((sheet) => sheet.getByRole('button', { name: /Delete project/ }).click());
  await expectAccessible(page, 'delete dialog');
});
