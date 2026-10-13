import { expect, test, type Page, type APIRequestContext } from '@playwright/test';
import { GeoJSONVT } from '@maplibre/geojson-vt';
import { fromGeojsonVt } from '@maplibre/vt-pbf';

const parcel = { type: 'Polygon' as const, coordinates: [[[106.7605,10.8205],[106.762,10.8205],[106.762,10.822],[106.7605,10.822],[106.7605,10.8205]]] };
async function clickMap(page: Page, coordinates: number[]) {
  const p = await page.evaluate(`window.dataMap.project(${JSON.stringify(coordinates)})`) as { x: number; y: number };
  await page.mouse.click(p.x, p.y);
}
async function buildingHeights(page: Page) {
  return page.evaluate(() => window.dataMap.querySourceFeatures('development-scene').filter(f => f.properties.kind === 'building').map(f => f.properties.height));
}
async function prepare(page: Page, request: APIRequestContext) {
  const fixtureStyle = { version: 8, sources: { baseline: { type: 'geojson', data: { type: 'FeatureCollection', features: [
    { type: 'Feature', id: 77, properties: {}, geometry: { type: 'Polygon', coordinates: [[[106.761,10.821],[106.7614,10.821],[106.7614,10.8214],[106.761,10.8214],[106.761,10.821]]] } },
  ] } } }, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#dce5df' } },
    { id: 'baseline-buildings', type: 'fill-extrusion', source: 'baseline', paint: { 'fill-extrusion-color': '#a9b6ae', 'fill-extrusion-height': 6 } }] };
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: fixtureStyle }));
  await page.route('https://tiles.mapterhorn.com/**', route => route.abort());
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [{ id: 'parcels', available: true }] } }));
  const tiles = new GeoJSONVT({ type: 'Feature', properties: { parcel_id: '3885881' }, geometry: parcel }, { maxZoom: 18 });
  await page.route('**/parcels/tiles/**', route => {
    const match = route.request().url().match(/tiles\/(\d+)\/(\d+)\/(\d+)\.pbf/)!;
    const tile = tiles.getTile(+match[1], +match[2], +match[3]);
    return tile ? route.fulfill({ contentType: 'application/vnd.mapbox-vector-tile', body: Buffer.from(fromGeojsonVt({ features: tile })) }) : route.fulfill({ status: 204 });
  });
  const name = `Development ${Date.now()}`;
  const plan = await (await request.post('/api/v1/zoning/plans', { data: { name, study_area: { type: 'Polygon', coordinates: [
    [[106.76,10.82],[106.763,10.82],[106.763,10.823],[106.76,10.823],[106.76,10.82]],
  ] } } })).json();
  return { plan, name, fixtureStyle };
}

test('real API: parcel picking, draft, save, clone, edit, lock, masks, style restore and reload', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const { plan, name, fixtureStyle } = await prepare(page, request);
  await page.goto('/tests/browser/data-layers.html');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list li > button:first-child').filter({ hasText: name }).click();
  await page.getByRole('button', { name: 'Development', exact: true }).click();
  await page.waitForFunction(() => !!window.dataMap.getLayer('zoning-plan-parcels-pick') && window.dataMap.isStyleLoaded() && !window.dataMap.isMoving());
  await clickMap(page, [106.7607,10.8207]);
  await expect(page.getByText('Parcel 3885881', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Draw building', exact: true }).click();
  for (const p of [[106.7607,10.8207],[106.76095,10.8207],[106.76095,10.82095],[106.7607,10.82095]]) await clickMap(page, p);
  await page.getByLabel('Building name').fill('House A');
  await page.getByRole('button', { name: 'Existing', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Unsaved proposal' })).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  await expect(page.getByText('Official limits: Unknown. Proposed limits are assumptions.')).toBeVisible();
  await page.route(`**/api/v1/zoning/plans/${plan.id}/commands`, route => route.fulfill({ status: 503, json: { detail: 'Temporary test outage' } }), { times: 1 });
  await page.getByRole('button', { name: 'Save proposal', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Temporary test outage');
  await expect(page.getByLabel('Building name')).toHaveValue('House A');
  await page.getByRole('button', { name: 'Save proposal', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Saved · revision 2' })).toBeVisible();
  await expect.poll(() => buildingHeights(page)).toContain(6.4);
  await page.getByRole('button', { name: 'Duplicate scenario', exact: true }).click();
  await page.getByRole('dialog').getByLabel('Name', { exact: true }).fill('Scenario B');
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Scenario B', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.locator('.development-list button').first().click();
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByLabel('Floors', { exact: true }).fill('4');
  await page.getByRole('button', { name: 'Save proposal', exact: true }).click();
  await page.waitForFunction(() => window.dataMap.isStyleLoaded() && !window.dataMap.isMoving());
  await expect.poll(() => buildingHeights(page)).toContain(12.8);
  await page.getByRole('button', { name: 'Duplicate', exact: true }).click();
  await page.getByRole('button', { name: 'Save proposal', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('overlap');
  await page.getByRole('button', { name: 'Scenario A', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Discard', exact: true }).click();
  await page.getByRole('button', { name: 'Scenario B', exact: true }).click();
  await page.locator('.development-list button').first().click();
  await page.getByRole('button', { name: 'Demolish parcel', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.dataMap.getFilter('baseline-buildings'))).not.toBeUndefined();
  await expect.poll(() => page.evaluate(() => window.dataMap.queryRenderedFeatures({ layers: ['baseline-buildings'] }).length)).toBe(0);
  await page.getByRole('button', { name: 'Scenario A', exact: true }).click();
  await expect.poll(() => buildingHeights(page)).toContain(6.4);
  await expect.poll(() => page.evaluate(() => window.dataMap.getFilter('baseline-buildings') ?? null)).toBeNull();
  await page.getByRole('button', { name: 'Existing', exact: true }).click();
  await expect.poll(() => buildingHeights(page)).toEqual([]);
  await page.getByRole('button', { name: 'Scenario B', exact: true }).click();
  await expect.poll(() => buildingHeights(page)).toContain(12.8);
  await page.getByRole('button', { name: 'Scenario options', exact: true }).click();
  await page.getByRole('button', { name: 'Lock scenario', exact: true }).click();
  await page.locator('.development-list button').first().click();
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toBeDisabled();
  await page.evaluate(style => window.dataMap.setStyle(style as Parameters<typeof window.dataMap.setStyle>[0]), fixtureStyle);
  await page.waitForFunction(() => !!window.dataMap.getLayer('development-buildings') && window.dataMap.isStyleLoaded());
  await expect.poll(() => buildingHeights(page)).toContain(12.8);
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Development comparison' })).toContainText('Proposed GFA');
  await page.screenshot({ path: '../.runtime/development/comparison.png' });
  await page.reload();
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list li > button:first-child').filter({ hasText: name }).click();
  await page.getByRole('button', { name: 'Scenario B', exact: true }).click();
  await page.getByRole('button', { name: 'Development', exact: true }).click();
  await page.locator('.development-list button').first().click();
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toBeDisabled();
  await expect.poll(() => buildingHeights(page)).toContain(12.8);
  await page.getByRole('region', { name: 'Development editor' }).getByRole('button', { name: '3D', exact: true }).click();
  await page.waitForFunction(() => window.dataMap.getPitch() > 40 && !window.dataMap.isMoving());
  await page.screenshot({ path: '../.runtime/development/massing-3d.png' });
  await page.getByRole('region', { name: 'Development editor' }).getByRole('button', { name: '2D', exact: true }).click();
  await page.waitForFunction(() => window.dataMap.getPitch() === 0 && !window.dataMap.isMoving());
  for (const width of [1440, 1024, 768, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.getByLabel('Plan details')).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (width === 1440 || width === 320) await page.screenshot({ path: `../.runtime/development/sidebar-${width}.png` });
  }
  const saved = await (await request.get(`/api/v1/zoning/plans/${plan.id}`)).json();
  expect(saved.scenarios[0].buildings).toEqual([]);
  expect(saved.scenarios[1].buildings[0].height_m).toBe(6.4);
  expect(saved.scenarios[2].buildings[0].height_m).toBe(12.8);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: 'Duplicate scenario', exact: true }).click();
  await page.getByRole('dialog').getByLabel('Name', { exact: true }).fill('Low-rise test');
  await page.getByRole('dialog').getByRole('combobox', { name: 'Based on', exact: true }).selectOption(plan.scenarios[0].id);
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click();
  await page.evaluate(() => window.dataMap.jumpTo({ center: [106.76125,10.82125], zoom: 17, pitch: 0 }));
  await page.waitForFunction(() => window.dataMap.isStyleLoaded() && !window.dataMap.isMoving());
  await clickMap(page, [106.7607,10.8207]);
  await expect(page.getByText('Parcel 3885881', { exact: true })).toBeVisible();
  await page.getByText('Apply building type', { exact: true }).click();
  await page.getByRole('button', { name: 'Preview type', exact: true }).click();
  await expect(page.getByLabel('Building name')).toHaveValue('Low-rise proposal');
  await page.getByRole('button', { name: 'Save proposal', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Low-rise proposal', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test('mixed floor uses: preview, metrics, 2D picking, save, reload and floor removal', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const { plan, name } = await prepare(page, request);
  await page.goto('/tests/browser/data-layers.html');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list li > button:first-child').filter({ hasText: name }).click();
  await page.getByRole('button', { name: 'Development', exact: true }).click();
  await page.waitForFunction(() => !!window.dataMap.getLayer('zoning-plan-parcels-pick') && window.dataMap.isStyleLoaded() && !window.dataMap.isMoving());
  await clickMap(page, [106.7607,10.8207]);
  await page.getByText('Apply building type', { exact: true }).click();
  await page.getByRole('button', { name: 'Preview type', exact: true }).click();
  await page.getByRole('button', { name: 'Save proposal', exact: true }).click();
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByRole('combobox', { name: 'Floor use', exact: true }).selectOption('commercial');
  await page.getByLabel('Floor height (m)', { exact: true }).fill('4.5');
  await page.getByRole('combobox', { name: 'Edit floor', exact: true }).selectOption('2');
  await page.getByRole('combobox', { name: 'Floor use', exact: true }).selectOption('office');
  await page.getByLabel('Floor height (m)', { exact: true }).fill('3.6');
  await page.locator('.development-floor-editor').getByLabel('GFA', { exact: true }).uncheck();
  await page.getByRole('button', { name: 'Preview', exact: true }).click();
  await page.waitForFunction(() => window.dataMap.getPitch() > 40 && !window.dataMap.isMoving());
  await expect.poll(() => buildingHeights(page)).toContain(8.1);
  await page.screenshot({ path: '../.runtime/development/mixed-floor-preview.png' });
  await page.getByRole('button', { name: 'Save proposal', exact: true }).click();
  await expect(page.locator('.development-floor-table')).toContainText('Commercial');
  await expect(page.locator('.development-floor-table')).toContainText('Office');
  const mixed = await (await request.get(`/api/v1/zoning/plans/${plan.id}`)).json();
  const mixedScenario = mixed.scenarios.find((s: { name: string }) => s.name === 'Scenario A');
  const proposal = mixedScenario.buildings[0];
  expect(proposal.height_m).toBeCloseTo(8.1);
  expect(mixedScenario.development_metrics.gfa_m2).toBeCloseTo(proposal.footprint_m2, 1);
  expect(mixedScenario.development_metrics.space_use_m2.office).toBe(0);
  await page.getByRole('region', { name: 'Development editor' }).getByRole('button', { name: '2D', exact: true }).click();
  await page.waitForFunction(() => window.dataMap.getPitch() === 0 && !window.dataMap.isMoving());
  expect(await page.evaluate(() => window.dataMap.getLayoutProperty('development-buildings', 'visibility'))).toBe('none');
  expect(await page.evaluate(() => window.dataMap.getLayoutProperty('development-excluded-floors', 'visibility'))).toBe('none');
  expect(await page.evaluate(() => window.dataMap.getLayoutProperty('development-building-footprints', 'visibility'))).toBe('visible');
  await page.waitForFunction(() => window.dataMap.isStyleLoaded());
  await clickMap(page, [106.7606,10.8206]);
  await expect(page.locator('.development-building')).toHaveCount(0);
  await clickMap(page, [106.76125,10.82125]);
  await expect(page.locator('.development-building')).toBeVisible();
  // Persisted mixed floors survive reload and remain editable in 2D.
  await page.reload();
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list li > button:first-child').filter({ hasText: name }).click();
  await page.getByRole('button', { name: 'Development', exact: true }).click();
  await page.locator('.development-list button').first().click();
  await expect(page.locator('.development-floor-table')).toContainText('Office');
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.getByRole('combobox', { name: 'Edit floor', exact: true }).selectOption('2');
  await page.waitForFunction(() => !!window.dataMap.getLayer('zoning-vertices') && window.dataMap.queryRenderedFeatures({ layers: ['zoning-vertices'] }).length > 0);
  await expect(page.getByRole('combobox', { name: 'Floor use', exact: true })).toHaveValue('office');
  await expect(page.locator('.development-floor-editor').getByLabel('GFA', { exact: true })).not.toBeChecked();
  await page.screenshot({ path: '../.runtime/development/mixed-floor-editor.png' });
  await page.setViewportSize({ width: 320, height: 900 });
  await page.getByRole('combobox', { name: 'Edit floor', exact: true }).scrollIntoViewIfNeeded();
  await expect(page.getByRole('combobox', { name: 'Floor use', exact: true })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '../.runtime/development/mixed-floor-mobile.png' });
  await page.getByLabel('Floors', { exact: true }).fill('1');
  await page.getByRole('button', { name: 'Save proposal', exact: true }).click();
  await expect(page.locator('.development-floor-table tbody tr')).toHaveCount(1);
  expect(errors).toEqual([]);
});
