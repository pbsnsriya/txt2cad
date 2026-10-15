// Runs against the real model (Gemini) and costs a few cents: only with E2E_LIVE=1 and GEMINI_API_KEY in backend/.env or the environment.
import { API, build, composer, expect, HOUSE, projects, resetProjects, test } from './helpers';

test.beforeEach(({ request }) => resetProjects(request));

async function pickGemini(page: import('@playwright/test').Page) {
  await page.getByRole('button', { name: /Practice mode/ }).click();
  await page.getByRole('menuitem', { name: /Gemini/ }).click();
}

test('F02-H1 live: build a house, then add a study next to the kitchen', async ({ page, request }) => {
  await page.goto('/');
  await pickGemini(page);
  await composer(page).fill(HOUSE);
  await composer(page).press('Enter');
  await expect(page.getByText(/Version 1:/).first()).toBeVisible({ timeout: 180_000 });
  await expect(page.getByTestId('viewer').getByText(/v1 · \d+ elements/)).toBeVisible();
  await composer(page).fill('Add a study on the ground floor next to the kitchen.');
  await composer(page).press('Enter');
  await expect(page.getByText(/Version 2:/).first()).toBeVisible({ timeout: 180_000 });
  const [project] = await projects(request);
  const head = (await (await request.get(`${API}/api/projects/${project.id}`)).json()).head;
  expect(head.number).toBe(2);
  expect(head.design.rooms.some((r: { name: string; level: string }) => /study/i.test(r.name) && r.level === 'L1')).toBe(true);
  expect(await projects(request)).toHaveLength(1);                       // the edit did not open a second project
});
