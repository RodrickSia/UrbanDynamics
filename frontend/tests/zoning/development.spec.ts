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
    { type: 'Feature', id: 78, properties: {}, geometry: { type: 'Polygon', coordinates: [[[106.764,10.821],[106.7644,10.821],[106.7644,10.8214],[106.764,10.8214],[106.764,10.821]]] } },
  ] } } }, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#dce5df' } },
    { id: 'urban-buildings-3d', type: 'fill-extrusion', source: 'baseline', paint: { 'fill-extrusion-color': '#a9b6ae', 'fill-extrusion-height': 6 } }] };
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

test('zone site takes priority over parcels; drawing panel sits left and indicator chart scopes buildings', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const prepared = await prepare(page, request);
  let plan = prepared.plan;
  const command = async (action: string, payload: object) => {
    const response = await request.post(`/api/v1/zoning/plans/${plan.id}/commands`, { data: {
      revision: plan.revision, scenario_id: plan.scenarios[1].id, action, payload,
    } });
    expect(response.ok(), await response.text()).toBe(true);
    plan = await response.json();
  };
  await command('add_type', { type: { code: 'ODT', name: 'Residential', color: '#D79B8C' } });
  await command('draw', { geometry: plan.study_area, type_id: plan.types[0].id, policy: 'preserve' });
  await page.goto('/tests/browser/data-layers.html');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list .zoning-plan-open').filter({ hasText: prepared.name }).click();
  await page.getByRole('button', { name: 'Draw zone', exact: true }).click();
  const bounds = await page.getByLabel('Zoning tools').boundingBox();
  expect(bounds!.x).toBeLessThan(25);
  expect(bounds!.y + bounds!.height).toBeGreaterThan(950);
  await page.screenshot({ path: '../.runtime/zone-chart-e2e/draw-left.png' });
  await page.getByRole('button', { name: 'Cancel geometry edit' }).click();
  await page.getByRole('button', { name: 'Development', exact: true }).click();
  await page.waitForFunction(() => !!window.dataMap.getLayer('zoning-plan-parcels-pick') && window.dataMap.isStyleLoaded() && !window.dataMap.isMoving());
  await clickMap(page, [106.7607,10.8207]);
  await expect(page.locator('.development-parcel')).toContainText('Zoning · ODT');
  await page.getByRole('button', { name: 'Draw building', exact: true }).click();
  await expect(page.getByText('Hide baseline on this parcel')).toHaveCount(0);
  // This footprint extends beyond the cadastral parcel, but stays in the zoning site.
  await page.keyboard.down('Control');
  for (const p of [[106.7615,10.8215],[106.7625,10.8215],[106.7625,10.8225],[106.7615,10.8225]]) await clickMap(page, p);
  await page.keyboard.up('Control');
  await page.getByRole('button', { name: 'Save proposal', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Saved · revision 4' })).toBeVisible();
  const saved = await (await request.get(`/api/v1/zoning/plans/${plan.id}`)).json();
  expect(saved.scenarios[1].buildings[0].parcel_id).toBe(`zone:${plan.scenarios[1].zones[0].id}`);
  await page.route('**/api/v1/indicators/area', route => {
    const body = route.request().postDataJSON();
    const metrics = { population: 100, energy_kwh_day: 300, water_m3_day: 12, waste_kg_day: 100,
      housing_capacity: null, jobs_needed: 50, jobs_capacity: null, jobs_balance: null };
    return route.fulfill({ json: { geometry: body.geometry, area_m2: 10000, baseline: metrics,
      proposal: body.include_scenario ? { ...metrics, population: 200 } : null, land_use: [], zoning: [],
      population_source: { status: 'available', year: 2025, coverage_percent: 100 },
      transit: { status: 'missing', coverage_percent: null }, assumptions: body.assumptions, notes: [], issues: [] } });
  });
  await page.getByRole('button', { name: 'Indicators', exact: true }).click();
  await page.getByRole('button', { name: 'Draw area', exact: true }).click();
  await page.keyboard.down('Control');
  for (const p of [[106.7607,10.8207],[106.7615,10.8207],[106.7615,10.8215],[106.7607,10.8215]]) await clickMap(page, p);
  await page.keyboard.up('Control');
  await page.getByRole('button', { name: 'Analyze area' }).click();
  await page.getByRole('button', { name: 'Show 3D chart', exact: true }).click();
  await expect.poll(() => page.evaluate(() => ({ chart: !!window.dataMap.getLayer('indicator-chart-bars'),
    pitched: window.dataMap.getPitch() > 40, moving: window.dataMap.isMoving() })), { timeout: 15000 }).toEqual({ chart: true, pitched: true, moving: false });
  await expect.poll(() => page.evaluate(() => window.dataMap.getStyle().sources['indicator-chart'].data.features.length)).toBe(2);
  await expect.poll(() => page.evaluate(() => window.dataMap.getStyle().sources['development-scene'].data.features.filter(f => f.properties.kind === 'building').length)).toBe(0);
  await expect.poll(() => page.evaluate(() => window.dataMap.getStyle().sources['plan-scope-urban-buildings-3d'].data.features.map(f => f.id))).toEqual([77]);
  await page.screenshot({ path: '../.runtime/zone-chart-e2e/indicator-chart.png' });
  for (const width of [768, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByLabel('Include plan scenario').uncheck();
  await expect.poll(() => page.evaluate(() => window.dataMap.getStyle().sources['indicator-chart']?.data.features.length ?? 0)).toBe(1);
  await page.getByLabel('Chart metric').selectOption('housing_capacity');
  await expect(page.getByRole('region', { name: 'Map chart' })).toContainText('No data');
  await expect.poll(() => page.evaluate(() => window.dataMap.getStyle().sources['indicator-chart'].data.features.length)).toBe(0);
  await page.getByRole('button', { name: 'Indicators', exact: true }).click();
  await expect.poll(() => page.evaluate(() => !!window.dataMap.getSource('indicator-chart'))).toBe(false);
  await expect.poll(() => page.evaluate(() => !!window.dataMap.getSource('plan-scope-urban-buildings-3d'))).toBe(false);
  expect(await page.evaluate(() => window.dataMap.getPaintProperty('urban-buildings-3d', 'fill-extrusion-opacity'))).toBeGreaterThan(0);
  expect(errors).toEqual([]);
});

test('Existing reads streamed Goong buildings and measures scenario setbacks in 2D and 3D', async ({ page, request }) => {
  const { name } = await prepare(page, request);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const buildings = new GeoJSONVT({ type: 'Feature', id: 101, properties: { height: 24, levels: 6 },
    geometry: { type: 'Polygon', coordinates: [[[106.7606,10.8206],[106.7609,10.8206],[106.7609,10.8209],[106.7606,10.8209],[106.7606,10.8206]]] } }, { maxZoom: 18 });
  await page.unroute('https://tiles.goong.io/**');
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: {
    version: 8, sources: { composite: { type: 'vector', tiles: ['http://127.0.0.1:5178/__baseline/{z}/{x}/{y}.pbf'], maxzoom: 18 } },
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#dce5df' } },
      { id: 'building-footprints', type: 'fill', source: 'composite', 'source-layer': 'VN_Building', paint: { 'fill-opacity': 0 } }],
  } }));
  await page.route('**/__baseline/**', route => {
    const match = route.request().url().match(/__baseline\/(\d+)\/(\d+)\/(\d+)\.pbf/)!;
    const tile = buildings.getTile(+match[1], +match[2], +match[3]);
    return tile ? route.fulfill({ contentType: 'application/vnd.mapbox-vector-tile', body: Buffer.from(fromGeojsonVt({ VN_Building: tile })) }) : route.fulfill({ status: 204 });
  });
  await page.goto('/tests/browser/data-layers.html');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list .zoning-plan-open').filter({ hasText: name }).click();
  await page.getByRole('button', { name: 'Development', exact: true }).click();
  await page.waitForFunction(() => !!window.dataMap.getLayer('zoning-plan-parcels-pick') && window.dataMap.isStyleLoaded() && !window.dataMap.isMoving());
  await clickMap(page, [106.7607,10.8207]);
  const panel = page.getByRole('region', { name: 'Development editor' });
  await expect(panel.getByText('Mapped buildings · Goong loaded tiles · estimated floors/heights')).toBeVisible();
  await expect(panel.getByRole('row', { name: /^Height / })).toContainText('24 m');
  await expect(panel.getByRole('row', { name: /^Floors / })).toContainText('6 floors');
  const setback = panel.getByRole('row', { name: /^Min. setback / });
  await expect(setback).not.toContainText('No data');
  await page.getByRole('button', { name: 'Existing', exact: true }).click();
  await page.waitForFunction(() => window.dataMap.isStyleLoaded() && !window.dataMap.isMoving());
  await clickMap(page, [106.7607,10.8207]);
  await expect(panel.getByRole('row', { name: /^Height / })).toContainText('24 m');
  await expect(setback).not.toContainText('No data');
  await panel.getByRole('button', { name: '3D', exact: true }).click();
  await panel.getByRole('button', { name: '2D', exact: true }).click();
  await expect(panel.getByRole('row', { name: /^Height / })).toContainText('24 m');
  await panel.screenshot({ path: '../.runtime/development-gap-e2e/existing-baseline.png' });
  expect(errors).toEqual([]);
});

test('real API: parcel picking, draft, save, clone, edit, lock, masks, style restore and dashboard', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const { plan, name, fixtureStyle } = await prepare(page, request);
  await page.goto('/tests/browser/data-layers.html');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list .zoning-plan-open').filter({ hasText: name }).click();
  await page.getByRole('button', { name: 'Development', exact: true }).click();
  await page.waitForFunction(() => !!window.dataMap.getLayer('zoning-plan-parcels-pick') && window.dataMap.isStyleLoaded() && !window.dataMap.isMoving());
  await clickMap(page, [106.7607,10.8207]);
  await expect(page.locator('.development-parcel').getByText('Parcel 3885881', { exact: true })).toBeVisible();
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
  await expect.poll(() => page.evaluate(() => window.dataMap.getPaintProperty('urban-buildings-3d', 'fill-extrusion-opacity'))).toBe(0);
  await expect.poll(() => page.evaluate(() => window.dataMap.querySourceFeatures('plan-scope-urban-buildings-3d').length)).toBe(0);
  await page.getByRole('button', { name: 'Scenario A', exact: true }).click();
  await expect.poll(() => buildingHeights(page)).toContain(6.4);
  await page.getByRole('region', { name: 'Development editor' }).getByRole('button', { name: '3D', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.dataMap.querySourceFeatures('plan-scope-urban-buildings-3d').length)).toBeGreaterThan(0);
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
  await expect(page.getByRole('button',{name:'Draw area',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Study area',exact:true})).toHaveCount(0);
  await page.getByText('Plan comparison & validation',{exact:true}).click();
  await expect(page.getByRole('region', { name: 'Development comparison' })).toContainText('Proposed GFA');
  expect(errors).toEqual([]);
});

test('persisted locked proposals reload, resize and generate a new building type', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const prepared = await prepare(page, request);
  const name = prepared.name;
  let plan = prepared.plan;
  const command = async (action: string, payload: object, scenarioId: string) => {
    const response = await request.post(`/api/v1/zoning/plans/${plan.id}/commands`, { data: {
      revision: plan.revision, scenario_id: scenarioId, action, payload,
    } });
    expect(response.ok()).toBe(true);
    plan = await response.json();
  };
  const input = { parcel_id: '3885881', name: 'House A', geometry: { type: 'Polygon', coordinates: [
    [[106.7607,10.8207],[106.76095,10.8207],[106.76095,10.82095],[106.7607,10.82095],[106.7607,10.8207]],
  ] }, floors: 2, floor_height: 3.2, space_use_id: 'residential' };
  await command('save_building', input, plan.scenarios[1].id);
  await command('add_scenario', { name: 'Scenario B' }, plan.scenarios[1].id);
  await command('save_building', { ...input, id: plan.scenarios[2].buildings[0].id, floors: 4 }, plan.scenarios[2].id);
  await command('lock_scenario', { locked: true }, plan.scenarios[2].id);
  await page.goto('/tests/browser/data-layers.html', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list .zoning-plan-open').filter({ hasText: name }).click();
  await page.getByRole('button', { name: 'Scenario B', exact: true }).click();
  await page.getByRole('button', { name: 'Development', exact: true }).click();
  await page.locator('.development-list button').first().click();
  await expect(page.getByRole('button', { name: 'Edit', exact: true })).toBeDisabled();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list .zoning-plan-open').filter({ hasText: name }).click();
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
  await expect(page.locator('.development-parcel').getByText('Parcel 3885881', { exact: true })).toBeVisible();
  await page.getByText('Apply building type', { exact: true }).click();
  await page.getByRole('button', { name: 'Preview type', exact: true }).click();
  await expect(page.getByLabel('Building name')).toHaveValue('Low-rise proposal');
  await page.getByRole('button', { name: 'Save proposal', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Low-rise proposal', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test('existing metrics, zoning precedence, selected-parcel simulation and cached 2D/3D clipping', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const prepared = await prepare(page, request);
  let plan = prepared.plan;
  const command = async (action: string, payload: object) => {
    const response = await request.post(`/api/v1/zoning/plans/${plan.id}/commands`, { data: {
      revision: plan.revision, scenario_id: plan.scenarios[1].id, action, payload,
    } });
    expect(response.ok()).toBe(true);
    plan = await response.json();
  };
  await command('add_type', { type: { code: 'TMD', name: 'Commercial proposal', color: '#C18EAD' } });
  await command('draw', { geometry: parcel, type_id: plan.types.at(-1).id, policy: 'replace' });
  await page.goto('/tests/browser/data-layers.html', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list .zoning-plan-open').filter({ hasText: plan.name }).click();
  await page.getByRole('button', { name: 'Development', exact: true }).click();
  const editor = page.getByRole('region', { name: 'Development editor' });
  const simulation = page.getByRole('region', { name: 'Development simulation' });
  await expect(simulation.getByRole('combobox', { name: 'Scope', exact: true })).toHaveValue('parcel');
  await expect(simulation.getByRole('button', { name: 'Run simulation' })).toBeDisabled();
  await page.waitForFunction(() => !!window.dataMap.getLayer('zoning-plan-parcels-pick') && window.dataMap.isStyleLoaded() && !window.dataMap.isMoving());
  await clickMap(page, [106.7607,10.8207]);
  await expect(editor.locator('.development-parcel')).toContainText('TMD · Commercial proposal');
  await expect(editor.locator('.development-parcel')).toContainText('Zoning · TMD');
  await expect(editor.getByRole('row', { name: /^Height / })).toContainText('12.8 m');
  await expect(editor.locator('.zoning-metrics strong').first()).not.toHaveText('0 m²');
  const freezeRequest = page.waitForRequest(request => request.url().endsWith('/simulation/runs') && request.method() === 'POST');
  await simulation.getByRole('button', { name: 'Run simulation' }).click();
  expect((await freezeRequest).postDataJSON().parcel_id).toBe(`zone:${plan.scenarios[1].zones[0].id}`);
  await expect(simulation.getByRole('heading', { name: 'Proposed demand' })).toBeVisible({ timeout: 45000 });
  await simulation.getByText('Change vs Existing', { exact: true }).click();
  const comparison = simulation.locator('details').filter({ has: page.getByText('Change vs Existing', { exact: true }) });
  await expect(comparison.getByRole('row', { name: /^Water/ })).not.toContainText('Unknown');
  await editor.getByRole('button', { name: '3D', exact: true }).click();
  await page.waitForFunction(() => window.dataMap.getPitch() > 40 && !window.dataMap.isMoving());
  await expect.poll(() => page.evaluate(() => window.dataMap.querySourceFeatures('plan-scope-urban-buildings-3d').map(f => f.id))).toContain(77);
  expect(await page.evaluate(() => window.dataMap.querySourceFeatures('plan-scope-urban-buildings-3d').map(f => f.id))).not.toContain(78);
  // The clipped source must remain mounted across mode toggles and provider paint changes.
  await page.evaluate(() => { Object.assign(window, { cachedPlanSource: window.dataMap.getSource('plan-scope-urban-buildings-3d') }); });
  for (const mode of ['2D', '3D', '2D']) {
    await editor.getByRole('button', { name: mode, exact: true }).click();
    await expect.poll(() => page.evaluate(() => window.dataMap.getLayoutProperty('plan-scope-urban-buildings-3d', 'visibility'))).toBe(mode === '2D' ? 'none' : 'visible');
    expect(await page.evaluate(() => window.dataMap.getSource('plan-scope-urban-buildings-3d') === (window as unknown as {cachedPlanSource: unknown}).cachedPlanSource)).toBe(true);
    expect(await page.evaluate(() => window.dataMap.getPaintProperty('urban-buildings-3d', 'fill-extrusion-opacity'))).toBe(0);
  }
  await page.getByRole('button', { name: 'Existing', exact: true }).click();
  await page.waitForFunction(() => !window.dataMap.isMoving());
  await clickMap(page, [106.7607,10.8207]);
  await expect(editor.getByText('Proposed GFA', { exact: true })).toHaveCount(0);
  await expect(editor.getByRole('row', { name: /^Height / })).toContainText('12.8 m');
  await expect(editor.locator('.development-parcel')).not.toContainText('TMD');
  await page.screenshot({ path: '../.runtime/development/existing-metrics.png' });
  expect(errors).toEqual([]);
});

test('mixed floor uses: preview, metrics, 2D picking, save, reload and floor removal', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const { plan, name } = await prepare(page, request);
  await page.goto('/tests/browser/data-layers.html');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list .zoning-plan-open').filter({ hasText: name }).click();
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
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list .zoning-plan-open').filter({ hasText: name }).click();
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
