import { build, CABIN, composer, expect, modelShown, newProject, openProjectByName, openProjects, projects, resetProjects, test } from './helpers';

test.beforeEach(({ request }) => resetProjects(request));

test('F07-H1 new project, reopening from the list and reloading all land on the right model', async ({ page }) => {
  await build(page, CABIN);
  await newProject(page);
  await expect(page.getByRole('heading', { name: 'Start with a sentence' })).toBeVisible();
  await openProjectByName(page, /cabin/i);
  await expect(page.getByText(/Version 1:/).first()).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('viewer').getByText(/v1 · \d+ elements/)).toBeVisible({ timeout: 20_000 });
});

test('F07-H2 deleting asks first, focuses the safe button, and Escape backs out', async ({ page, request }) => {
  await build(page, CABIN);
  const askToDelete = async () => (await openProjects(page)).getByRole('button', { name: /Delete project/ }).click();
  await askToDelete();
  const dialog = page.getByRole('alertdialog').or(page.getByRole('dialog', { name: 'Delete this project?' }));
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  expect(await projects(request)).toHaveLength(1);
  await askToDelete();
  await page.getByRole('dialog', { name: 'Delete this project?' }).getByRole('button', { name: 'Delete project' }).click();
  await expect.poll(async () => (await projects(request)).length).toBe(0);
  const sheet = await openProjects(page);
  await expect(sheet.getByText('No projects yet. Describe a building to start one.')).toBeVisible();
});

test('F07-E1 the Home screen lists earlier projects and opens one', async ({ page }) => {
  await build(page, CABIN);
  await newProject(page);
  await page.getByRole('region', { name: 'Pick up where you left off' }).getByRole('button').first().click();
  await modelShown(page, 1);
  await expect(page.getByText(/Version 1:/).first()).toBeVisible();
  await expect(composer(page)).toBeVisible();
});
