import { expect, test, type Page } from '@playwright/test';

async function mapClick(page: Page, coordinates: number[]) {
  const point = await page.evaluate(`window.dataMap.project(${JSON.stringify(coordinates)})`) as { x: number; y: number };
  await page.mouse.click(point.x, point.y);
}

test('create, edit, preview, scenario isolation, reload and map-style recovery with the real zoning API', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: { version: 8, sources: {},
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#cbdcd7' } }] } }));
  await page.route('https://satellite.goong.io/**', route => route.fulfill({ contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK1cAAAAASUVORK5CYII=', 'base64') }));
  // Only unrelated dataset discovery is stubbed. Every plan command reaches FastAPI.
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [{ id: 'parcels', available: true }] } }));
  await page.route('**/parcels/tiles/**', route => route.fulfill({ status: 204 }));
  await page.goto('/tests/browser/data-layers.html');
  await page.waitForFunction('window.dataMap?.isStyleLoaded()');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.getByRole('button', { name: 'New plan', exact: true }).click();
  await page.evaluate('window.dataMap.jumpTo({center:[106.762,10.821],zoom:16})');
  const name = `Zoning browser ${Date.now()}`;
  await page.getByLabel('Plan name', { exact: true }).fill(name);
  for (const p of [[106.76, 10.82], [106.764, 10.82], [106.764, 10.824], [106.76, 10.824]]) await mapClick(page, p);
  await page.getByRole('button', { name: 'Create plan', exact: true }).click();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  await page.waitForFunction(() => !!window.dataMap.getLayer('zoning-plan-parcels-outline'));
  expect(await page.evaluate(() => {
    const map = window.dataMap;
    return { fill: !!map.getLayer('zoning-plan-parcels-fill'), ordinary: !!map.getLayer('dataset-parcels'),
      tiles: (map.getSource('zoning-plan-parcels') as { serialize: () => { tiles: string[] } }).serialize().tiles };
  })).toMatchObject({ fill: false, ordinary: false, tiles: [expect.stringContaining('/parcels/tiles/')] });
  await page.getByRole('button', { name: 'Add zoning type' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Code', { exact: true }).fill('MU');
  await dialog.getByLabel('Name', { exact: true }).fill('Mixed-use proposal');
  await dialog.getByLabel('FAR', { exact: true }).fill('4');
  await dialog.getByLabel('Coverage (%)', { exact: true }).fill('60');
  await dialog.getByRole('button', { name: 'Save type', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.waitForFunction('!window.dataMap.isMoving()');
  await page.getByRole('button', { name: 'Draw zone', exact: true }).click();
  for (const p of [[106.7605, 10.8205], [106.762, 10.8205], [106.762, 10.8235], [106.7605, 10.8235]]) await mapClick(page, p);
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  await expect(page.getByText('Preview ready', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Confirm zoning', exact: true }).click();
  await expect(page.getByText('Saved · revision 3', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Duplicate scenario', exact: true }).click();
  await page.getByRole('dialog').getByLabel('Name', { exact: true }).fill('Phase 1');
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Phase 1', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.waitForFunction('window.dataMap.queryRenderedFeatures({layers:["zoning-fill"]}).some(f=>f.properties.kind==="zone")');
  await mapClick(page, [106.761, 10.822]);
  await expect(page.getByRole('complementary', { name: 'Zone inspector', exact: true })).toContainText('Unknown');
  await page.getByRole('button', { name: 'Delete zone', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByText('Saved · revision 5', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Scenario A', exact: true }).click();
  await page.waitForFunction('window.dataMap.queryRenderedFeatures({layers:["zoning-fill"]}).some(f=>f.properties.kind==="zone")');
  await page.getByRole('button', { name: 'Existing', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Draw zone', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Scenario A', exact: true }).click();
  // Style reload must recreate map sources without resetting persisted geometry.
  await page.evaluate('window.dataMap.setStyle({version:8,sources:{},layers:[{id:"new-background",type:"background",paint:{"background-color":"#d6e5df"}}]})');
  await page.waitForFunction('window.dataMap.getLayer("zoning-fill") && window.dataMap.isStyleLoaded()');
  await page.getByRole('button', { name: 'Indicators', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Zone distribution', exact: true })).toBeVisible();
  await expect(page.getByLabel('Indicators panel')).toContainText('Insufficient authoritative data');
  await page.screenshot({ path: 'test-results/zoning-indicators-desktop.png' });
  await page.reload();
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list li > button:first-child').filter({ hasText: name }).click();
  await expect(page.getByRole('button', { name: 'Phase 1', exact: true })).toBeVisible();
  await expect(page.getByText('Saved · revision 5', { exact: true })).toBeVisible();
  await page.waitForFunction('window.dataMap.getLayer("zoning-fill") && window.dataMap.getZoom() > 14 && !window.dataMap.isMoving()');
  await page.screenshot({ path: 'test-results/zoning-plans-desktop.png' });
  for (const width of [320, 768, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.getByRole('button', { name: 'Plans', exact: true })).toBeInViewport();
    await expect(page.getByLabel('Plans panel')).toBeInViewport();
    expect(await page.evaluate('document.documentElement.scrollWidth <= innerWidth')).toBe(true);
    await page.screenshot({ path: `test-results/zoning-plans-${width}.png` });
  }
  expect(errors).toEqual([]);
});

test('deleting a plan from the sidebar removes its saved scenarios', async ({ page, request }) => {
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: { version: 8, sources: {},
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#cbdcd7' } }] } }));
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [] } }));
  const plan = await (await request.post('/api/v1/zoning/plans', { data: { name: `Delete browser ${Date.now()}`,
    study_area: { type: 'Polygon', coordinates: [[[106.76, 10.82], [106.764, 10.82],
      [106.764, 10.824], [106.76, 10.824], [106.76, 10.82]]] } } })).json();
  await page.goto('/tests/browser/data-layers.html');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  const row = page.locator('.zoning-plan-list li').filter({ hasText: plan.name });
  await row.getByRole('button', { name: `Delete plan ${plan.name}` }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click();
  await expect(row).toHaveCount(0);
  expect((await request.get(`/api/v1/zoning/plans/${plan.id}`)).status()).toBe(404);
});

test('vertex editing, split/merge, undo and exclusive measurement ownership', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: { version: 8, sources: {},
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#cbdcd7' } }] } }));
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [] } }));
  const polygon = (west: number, east: number, south: number, north: number) => ({ type: 'Polygon',
    coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]] });
  let plan = await (await request.post('/api/v1/zoning/plans', { data: { name: `Geometry ${Date.now()}`,
    study_area: polygon(106.76, 106.764, 10.82, 10.824) } })).json();
  const send = async (action: string, payload: Record<string, unknown>) => {
    plan = await (await request.post(`/api/v1/zoning/plans/${plan.id}/commands`, { data: {
      revision: plan.revision, action, scenario_id: plan.scenarios[1].id, payload,
    } })).json();
  };
  await send('add_type', { type: { code: 'R', name: 'Residential proposal', color: '#55a99a' } });
  await send('draw', { type_id: plan.types[0].id, policy: 'preserve', geometry: polygon(106.7605, 106.762, 10.8205, 10.8235) });
  const originalArea = plan.scenarios[1].zones[0].area_m2;
  const saved = async () => (await request.get(`/api/v1/zoning/plans/${plan.id}`)).json();
  await page.goto('/tests/browser/data-layers.html');
  await page.waitForFunction('window.dataMap?.isStyleLoaded()');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list li > button:first-child').filter({ hasText: plan.name }).click();
  await page.waitForFunction('window.dataMap.getLayer("zoning-fill") && window.dataMap.getZoom() > 14 && !window.dataMap.isMoving()');
  await page.waitForFunction('window.dataMap.queryRenderedFeatures({layers:["zoning-fill"]}).some(f=>f.properties.kind==="zone")');
  await mapClick(page, [106.761, 10.822]);
  await page.getByRole('button', { name: 'Edit vertices', exact: true }).click();
  await page.waitForFunction('window.dataMap.queryRenderedFeatures({layers:["zoning-vertices"]}).length >= 8');
  const start = await page.evaluate('window.dataMap.project([106.7605,10.8235])') as { x: number; y: number };
  const end = await page.evaluate('window.dataMap.project([106.7608,10.8233])') as { x: number; y: number };
  await page.mouse.move(start.x, start.y); await page.mouse.down(); await page.mouse.move(end.x, end.y, { steps: 6 }); await page.mouse.up();
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm zoning', exact: true }).click();
  await expect.poll(async () => (await saved()).revision).toBe(4);
  expect((await saved()).scenarios[1].zones[0].area_m2).toBeLessThan(originalArea);
  await page.getByRole('button', { name: 'Undo geometry', exact: true }).click();
  await expect.poll(async () => (await saved()).scenarios[1].zones[0].area_m2).toBe(originalArea);
  await page.getByRole('button', { name: 'Split', exact: true }).click();
  await mapClick(page, [106.7602, 10.822]); await mapClick(page, [106.7623, 10.822]);
  await page.getByRole('button', { name: 'Apply split', exact: true }).click();
  await expect.poll(async () => (await saved()).scenarios[1].zones.length).toBe(2);
  await expect(page.getByText('Saved · revision 6', { exact: true })).toBeVisible();
  await page.waitForFunction('new Set(window.dataMap.queryRenderedFeatures({layers:["zoning-fill"]}).filter(f=>f.properties.kind==="zone").map(f=>f.properties.id)).size === 2');
  await mapClick(page, [106.761, 10.8227]);
  await expect(page.getByRole('complementary', { name: 'Zone inspector', exact: true })).toBeVisible();
  await page.keyboard.down('Shift'); await mapClick(page, [106.761, 10.821]); await page.keyboard.up('Shift');
  await page.getByRole('button', { name: 'Merge', exact: true }).click();
  await expect.poll(async () => (await saved()).scenarios[1].zones.length).toBe(1);
  await page.getByRole('button', { name: 'Measurement tools', exact: true }).click();
  await page.getByRole('button', { name: 'Measure distance', exact: true }).click();
  await expect(page.getByLabel('Plans panel')).toHaveCount(0);
  await expect.poll(() => page.evaluate('Boolean(window.dataMap.getSource("zoning-editor"))')).toBe(false);
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await expect(page.getByLabel('Plans panel')).toBeVisible();
  await expect.poll(() => page.evaluate('Boolean(window.dataMap.getSource("zoning-editor"))')).toBe(true);
  await page.getByRole('button', { name: 'Collapse zoning panel', exact: true }).click();
  await expect(page.getByLabel('Plans panel')).toBeHidden();
  await expect(page.getByRole('button', { name: 'Expand zoning panel', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
