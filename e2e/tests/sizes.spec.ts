import { API, build, expect, projects, resetProjects, test } from './helpers';

test.beforeEach(({ request }) => resetProjects(request));

const HOUSE = 'A one storey house with a kitchen, a living room and two bedrooms.';
const round = (n: number) => String(Math.round(n * 100) / 100);

test('F20-H1 sizes changed by hand save a new version with no model, and the table follows', async ({ page, request }) => {
  await build(page, HOUSE);
  const id = (await projects(request))[0].id;
  const before = await (await request.get(`${API}/api/projects/${id}`)).json();
  const room = before.head.design.rooms[0];
  await page.getByRole('tab', { name: 'Sizes' }).click();
  const width = page.getByLabel(`${room.name} width in metres`);
  await expect(width).toHaveAttribute('placeholder', round(room.rect[2]));
  await expect(page.getByRole('button', { name: 'Apply the change' })).toBeDisabled();
  await width.fill(String(room.rect[2] + 1));
  await page.getByRole('button', { name: 'Apply the change' }).click();
  await expect(page.getByTestId('sizes-message')).toContainText('Saved as a new version');
  const after = await (await request.get(`${API}/api/projects/${id}`)).json();
  expect(after.head.number).toBe(before.head.number + 1);
  expect(after.head.mode).toBe('ops');
  expect(after.head.summary).toContain('by hand');
  expect(after.head.design.rooms.find((r: { id: string }) => r.id === room.id).rect[2]).toBe(room.rect[2] + 1);
  await expect(page.getByLabel(`${room.name} width in metres`)).toHaveValue('');                        // the table starts again from the new version
  await expect(page.getByLabel(`${room.name} width in metres`)).toHaveAttribute('placeholder', round(room.rect[2] + 1));
  await expect(page.getByText(/v2 resized/)).toBeVisible();
});

test('F20-E1 a size that cannot be right is explained and cannot be applied', async ({ page }) => {
  await build(page, HOUSE);
  await page.getByRole('tab', { name: 'Sizes' }).click();
  const first = page.getByRole('row').nth(1).getByRole('textbox').first();
  await first.fill('0.5');
  await expect(page.getByRole('alert').first()).toContainText('between 1.5 and 40');
  await expect(page.getByRole('button', { name: 'Apply the change' })).toBeDisabled();
  await first.fill('');
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('F20-H2 the whole building can be made wider', async ({ page, request }) => {
  await build(page, HOUSE);
  const id = (await projects(request))[0].id;
  await page.getByRole('tab', { name: 'Sizes' }).click();
  await page.getByLabel('Building width in metres').fill('14');
  await page.getByRole('button', { name: 'Apply to the building' }).click();
  await expect(page.getByTestId('sizes-message')).toContainText('Saved as a new version');
  const head = (await (await request.get(`${API}/api/projects/${id}`)).json()).head;
  expect(head.summary).toContain('building');
});

test.describe('F20-E2 stale versions', () => {
  test.use({ allowErrors: [/Failed to load resource/] });                                             // the 409 is the point of the test

  test('an old tab that tries to change sizes gets a clear message and nothing is saved', async ({ page, request }) => {
    await build(page, HOUSE);
    const id = (await projects(request))[0].id;
    const head = (await (await request.get(`${API}/api/projects/${id}`)).json()).head;
    const room = head.design.rooms[0];
    await page.getByRole('tab', { name: 'Sizes' }).click();
    await page.getByLabel(`${room.name} width in metres`).fill(String(room.rect[2] + 1));
    // another tab changes the project first
    const other = await request.post(`${API}/api/projects/${id}/sizes`, { data: { base_version: head.number, rooms: [{ room: room.id, depth: room.rect[3] + 1 }] } });
    expect(other.status()).toBe(201);
    await page.getByRole('button', { name: 'Apply the change' }).click();
    await expect(page.getByTestId('sizes-message')).toContainText('no longer the latest');
    const now = await (await request.get(`${API}/api/projects/${id}`)).json();
    expect(now.head.number).toBe(head.number + 1);                                                      // only the other tab's change was saved
  });
});
