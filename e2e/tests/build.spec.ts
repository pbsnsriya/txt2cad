import { API, build, CABIN, composer, expect, HOUSE, openProjectByName, projects, resetProjects, test } from './helpers';

test.beforeEach(({ request }) => resetProjects(request));

test('F01-H1 a sentence becomes a checked, valid building', async ({ page, request }) => {
  await build(page);
  for (const phase of ['Setup', 'Rooms', 'Doors and stairs', 'Windows and roof']) await expect(page.getByText(phase, { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/\d+ met, 0 unmet/)).toBeVisible();
  await expect(page.locator('canvas')).toHaveCount(1);
  const [project] = await projects(request);
  const ifc = await (await request.get(`${API}/api/projects/${project.id}/versions/1/ifc`)).text();
  expect(ifc.startsWith('ISO-10303-21')).toBe(true);
  expect((ifc.match(/IFCWALL\(/g) ?? []).length).toBeGreaterThan(10);
  expect(ifc).toContain('IFCSTAIR(');                        // two storeys need a stair
});

test('F01-H2 a starter chip fills the box and does not send', async ({ page, request }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Cabin with one bedroom' }).click();
  await expect(composer(page)).toHaveValue(/cabin with one bedroom/i);
  expect(await projects(request)).toHaveLength(0);
});

test('F01-E1 empty and whitespace-only input cannot be sent', async ({ page, request }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Send' })).toBeDisabled();
  await composer(page).fill('   \n  ');
  await expect(page.getByRole('button', { name: 'Send' })).toBeDisabled();
  await composer(page).press('Enter');
  expect(await projects(request)).toHaveLength(0);
});

test.describe('F01-E2 a prompt over the length limit', () => {
  test.use({ allowErrors: [/Failed to load resource/] });
  test('is explained in words and leaves nothing half-made', async ({ page }) => {
    await page.goto('/');
    await composer(page).fill('a house '.repeat(1200));
    await composer(page).press('Enter');
    const alert = page.getByRole('alert').first();
    await expect(alert).toBeVisible();
    await expect(alert).not.toContainText('[object Object]');
    await expect(alert).toContainText(/too long|at most|characters|8000/i);
  });
});

test('F01-E3 emoji and accents survive the whole round trip', async ({ page }) => {
  const prompt = 'Casa de dos pisos con cocina 🏠, baño y tres dormitorios (café-bar), garaje';
  await build(page, prompt);
  await expect(page.getByText('Your request:', { exact: true }).locator('..')).toContainText('🏠');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Casa de dos pisos');
});

test('F01-E4 sending twice quickly makes one project and one run', async ({ page, request }) => {
  await page.goto('/');
  await composer(page).fill(CABIN);
  await composer(page).press('Enter');
  await composer(page).press('Enter').catch(() => undefined);          // the box may already be gone
  await expect(page.getByText(/Version 1:/).first()).toBeVisible({ timeout: 60_000 });
  expect(await projects(request)).toHaveLength(1);
});

test('F01-E5 reloading mid-run cancels that run cleanly and the session can simply be run again', async ({ page, request }) => {
  await page.goto('/');
  await composer(page).fill(HOUSE);
  await composer(page).press('Enter');
  await expect(page.getByText('Understanding the request')).toBeVisible();
  await page.reload();                                                    // closes the stream; the server stops the run
  await expect(page.getByRole('button', { name: 'Projects' })).toBeVisible();
  const [project] = await projects(request);
  expect(project.head_version_id).toBeNull();                              // nothing half-saved
  await openProjectByName(page, /Two storey house/);
  await expect(page.getByText('Say what to build in the box below.')).toBeVisible();
  await composer(page).fill(CABIN);
  await composer(page).press('Enter');
  await expect(page.getByText(/Version 1:/).first()).toBeVisible({ timeout: 60_000 });
});

test.describe('F01-E6 backend unreachable', () => {
  test.use({ allowErrors: [/Failed to load resource|ERR_FAILED|net::/] });
  test('says so and does not let the user type into the void', async ({ page }) => {
    await page.route(`${API}/**`, (r) => r.abort());     // the backend only; not the app's own src/api modules
    await page.goto('/');
    await expect(page.getByText('Server offline')).toBeVisible();
    await expect(composer(page)).toBeDisabled();
    await expect(page.getByRole('alert')).toContainText(/Cannot reach the backend/);
  });
});

test.describe('F01-E7 phone width and keyboard only', () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test('no sideways scroll and the whole flow works without a mouse', async ({ page }) => {
    await page.goto('/');
    for (let i = 0; i < 25 && !(await composer(page).evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press('Tab');
    await expect(composer(page)).toBeFocused();
    await page.keyboard.type(CABIN);
    await page.keyboard.press('Enter');
    await expect(page.getByText(/Version 1:/).first()).toBeVisible({ timeout: 60_000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    await page.getByRole('button', { name: 'Export' }).focus();
    await page.keyboard.press('Enter');
    await page.getByRole('menuitem', { name: /Floor plans \(\.dxf\)/ }).focus();
    const download = page.waitForEvent('download');
    await page.keyboard.press('Enter');
    expect((await download).suggestedFilename()).toMatch(/\.dxf$/);
  });
});
