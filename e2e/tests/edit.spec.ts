import { API, build, composer, expect, openProjectByName, projects, resetProjects, test } from './helpers';

test.beforeEach(({ request }) => resetProjects(request));

test('F02-E1 an edit the offline model cannot do is reported and keeps version 1', async ({ page, request }) => {
  await build(page);
  await composer(page).fill('add a basement');
  await composer(page).press('Enter');
  await expect(page.getByRole('alert').filter({ hasText: /could be applied/i })).toBeVisible({ timeout: 30_000 });
  const [project] = await projects(request);
  const detail = await (await request.get(`${API}/api/projects/${project.id}`)).json();
  expect(detail.head.number).toBe(1);
  expect(detail.versions).toHaveLength(1);
});

test('F02-E2 a second tab editing from an old version gets a clear 409', async ({ page, request }) => {
  await build(page);
  const [project] = await projects(request);
  await request.post(`${API}/api/projects/${project.id}/revert/1`);                      // another tab moved the project to version 2
  const stale = await request.post(`${API}/api/projects/${project.id}/runs`, { data: { prompt: 'add a study', base_version: 1 } });
  expect(stale.status()).toBe(409);
  expect((await stale.json()).detail).toMatch(/version 2, not 1/);
});

test('F04-H1 an older version can be opened and restored; history is never lost', async ({ page, request }) => {
  await build(page);
  const [project] = await projects(request);
  await request.post(`${API}/api/projects/${project.id}/revert/1`);                      // version 2
  await page.reload();
  await expect(page.getByRole('region', { name: 'Version history' })).toBeVisible({ timeout: 20_000 });
  const history = page.getByRole('region', { name: 'Version history' });
  await expect(history.getByText('v2 restored')).toBeVisible();
  await history.getByRole('button', { name: 'Open' }).last().click();                     // the list is newest first, so the last row is v1
  await expect(page.getByTestId('viewer').getByText(/^v1/)).toBeVisible();
  await history.getByRole('button', { name: 'Restore' }).first().click();                // restore v1 -> v3
  await expect(history.getByText('v3 restored')).toBeVisible();
  const detail = await (await request.get(`${API}/api/projects/${project.id}`)).json();
  expect(detail.versions.map((v: { number: number }) => v.number)).toEqual([1, 2, 3]);
});
