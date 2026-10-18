import fs from 'node:fs';
import { build, expect, resetProjects, test } from './helpers';

test.beforeEach(({ request }) => resetProjects(request));

test('F05-E1 nothing to export before something is built', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Export' })).toBeDisabled();
});

test('F05-H1 IFC, DXF, SVG and JSON download with readable names and real content', async ({ page }, info) => {
  await build(page);
  const get = async (item: RegExp) => {
    await page.getByRole('button', { name: 'Export' }).click();
    const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('menuitem', { name: item }).click()]);
    const file = info.outputPath(dl.suggestedFilename());
    await dl.saveAs(file);
    return { name: dl.suggestedFilename(), text: fs.readFileSync(file, 'utf8') };
  };
  const ifc = await get(/BIM file/);
  expect(ifc.name).toMatch(/^Two-storey-house.*-v1\.ifc$/);
  expect(ifc.text.startsWith('ISO-10303-21')).toBe(true);
  const dxf = await get(/Floor plans \(\.dxf\)/);
  expect(dxf.name).toMatch(/\.dxf$/);
  expect(dxf.text).toContain('AC1032');                    // R2018
  for (const layer of ['A-WALL', 'A-DOOR', 'A-GLAZ', 'A-FLOR-STRS', 'A-ANNO-DIMS']) expect(dxf.text).toContain(layer);
  const svg = await get(/Floor plans \(\.svg\)/);
  expect(svg.text).toContain('<svg');
  const spec = await get(/Geometry data/);
  expect(JSON.parse(spec.text).walls.length).toBeGreaterThan(10);
  const design = await get(/Design data/);
  expect(JSON.parse(design.text).levels).toHaveLength(2);
});

test('F05-E2 only formats this app really writes are offered', async ({ page }) => {
  await build(page);
  await page.getByRole('button', { name: 'Export' }).click();
  const items = await page.getByRole('menuitem').allInnerTexts();
  expect(items.join(' ')).not.toMatch(/STEP|DWG/);
  expect(items).toHaveLength(5);
});
