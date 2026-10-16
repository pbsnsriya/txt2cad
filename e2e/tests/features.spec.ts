import { API, build, CABIN, composer, expect, projects, resetProjects, test } from './helpers';

test.beforeEach(({ request }) => resetProjects(request));

test('F09-H1 stated sizes are measured and shown as asked against built', async ({ page }) => {
  await build(page, 'A one storey house with a living room 6 m by 4 m and a kitchen.');
  const line = page.getByText('The living room is 6.0 x 4.0 m').first();
  await expect(line).toBeVisible();
  await expect(line.locator('..')).toContainText('asked 6.0 x 4.0 m');       // the offline model does not try to hit it, but it is measured
});

test('F11-H1 a pitched roof is built, checked and shows in the quantities', async ({ page }) => {
  await build(page, 'A one storey house with a living room, a kitchen and two bedrooms, with a pitched roof.');
  const line = page.getByText('A gable roof').first();
  await expect(line).toBeVisible();
  await expect(line.locator('..')).toContainText('gable roof, 30 degrees');
  await page.getByRole('tab', { name: 'Quantities' }).click();
  await expect(page.getByText('Roof (gable, 30 deg)')).toBeVisible();
});

test('F12-H1 after a build the next requests are suggested, and picking one fills the box without sending', async ({ page }) => {
  await build(page, CABIN);
  const chips = page.getByTestId('suggestions');
  await expect(chips).toBeVisible();
  const posted: string[] = [];
  page.on('request', (r) => { if (r.method() === 'POST' && r.url().endsWith('/runs')) posted.push(r.url()); });
  await expect(chips.getByRole('button').first()).toHaveText('Give it a gable roof.');
  await chips.getByRole('button').first().click();
  await expect(composer(page)).toHaveValue('Give it a gable roof.');
  await page.waitForTimeout(400);
  expect(posted).toHaveLength(0);
});

test('F12-E1 no suggestions on the Home screen', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('suggestions')).toHaveCount(0);
});

test('F13-H1 three other layouts are built one after the other and saved as new versions', async ({ page, request }) => {
  await build(page, CABIN);
  await page.getByRole('button', { name: 'Try 3 other layouts' }).click();
  await expect(page.getByText(/Version 4:/).first()).toBeVisible({ timeout: 60_000 });
  const [project] = await projects(request);
  const detail = await (await request.get(`${API}/api/projects/${project.id}`)).json();
  expect(detail.versions.map((v: { number: number }) => v.number)).toEqual([1, 2, 3, 4]);
  const history = page.getByRole('region', { name: 'Version history' });
  for (const [k, label] of [[1, 'Compact'], [2, 'Open plan'], [3, 'Spine']] as const) {
    await expect(history.getByText(new RegExp(`Layout option ${k} \\(${label}\\)`)).first()).toBeVisible();
  }
});

test('F13-E1 stopping part way ends the series and keeps what was saved', async ({ page, request }) => {
  await build(page, CABIN);
  await page.getByRole('button', { name: 'Try 3 other layouts' }).click();
  await page.getByRole('button', { name: 'Stop' }).click();
  await expect(page.getByRole('button', { name: 'Try 3 other layouts' })).toBeEnabled({ timeout: 20_000 });
  const [project] = await projects(request);
  const detail = await (await request.get(`${API}/api/projects/${project.id}`)).json();
  expect(detail.versions.length).toBeLessThan(4);                           // the series stopped; nothing half-saved
  await expect(page.getByTestId('viewer').getByText(/v\d+ · \d+ elements/)).toBeVisible();
});

test('F14-H1 the data statement is on Home and in the model menu, and the offline model sends nothing off this computer', async ({ page }) => {
  const hosts = new Set<string>();
  page.on('request', (r) => { try { hosts.add(new URL(r.url()).hostname); } catch { /* data: urls */ } });
  await page.goto('/');
  await page.getByText('Where does my data go?').click();
  await expect(page.getByText(/saved on this computer only/)).toBeVisible();
  await expect(page.getByText(/Practice mode builds offline and sends nothing anywhere/)).toBeVisible();
  await page.getByRole('button', { name: /Practice mode/ }).click();
  await expect(page.getByRole('menuitem', { name: /Practice mode/ })).toContainText('Nothing is sent anywhere');
  await expect(page.getByRole('menuitem', { name: /Gemini/ })).toContainText('generativelanguage.googleapis.com');
  await page.keyboard.press('Escape');
  await composer(page).fill(CABIN);
  await composer(page).press('Enter');
  await expect(page.getByText(/Version 1:/).first()).toBeVisible({ timeout: 60_000 });
  const outside = [...hosts].filter((h) => h && !['127.0.0.1', 'localhost'].includes(h));
  expect(outside, 'requests to hosts other than this computer').toEqual([]);
});

test('F15-H1 a furnished house with finishes shows the Interiors phase, furniture and finishes in the quantities, and stops suggesting to furnish', async ({ page }) => {
  await build(page, 'A one storey house with a kitchen, a living room and two bedrooms, furnished, with oak floors and cream walls.');
  await expect(page.getByText('Interiors', { exact: true })).toBeVisible();
  await expect(page.getByText('The rooms are furnished').first()).toBeVisible();
  await page.getByRole('tab', { name: 'Quantities' }).click();
  await expect(page.getByText('Sofa', { exact: true })).toBeVisible();
  await expect(page.getByText('Floor finish: oak')).toBeVisible();
  await expect(page.getByText('Wall finish: cream')).toBeVisible();
  await page.getByRole('tab', { name: '3D view' }).click();
  await expect(page.getByTestId('suggestions')).not.toContainText('Furnish every room');
});

test('F15-H2 an unfurnished house is offered furniture and a floor', async ({ page }) => {
  await build(page, 'A one storey house with a kitchen, a living room and two bedrooms.');
  const chips = page.getByTestId('suggestions');
  await expect(chips).toContainText('Furnish every room.');
  await expect(chips).toContainText('oak floor');
});
