import { expect, test } from '@playwright/test';

test('planning buttons match map controls and slide below expanded search', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: {
    version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#cbdcd7' } }],
  } }));
  await page.route('https://satellite.goong.io/**', route => route.fulfill({ contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK1cAAAAASUVORK5CYII=', 'base64') }));
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [] } }));
  await page.route('**/api/v1/zoning/plans', route => route.fulfill({ json: { plans: [] } }));
  await page.goto('/tests/browser/data-layers.html');

  const nav = page.getByRole('navigation', { name: 'Planning workspace' });
  const plans = nav.getByRole('button', { name: 'Plans' });
  const indicators = nav.getByRole('button', { name: 'Indicators' });
  const rightControl = page.getByRole('button', { name: 'Zoom in' });
  const search = page.getByRole('searchbox', { name: 'Search places' });

  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const closed = await nav.boundingBox();
    const sizes = await page.evaluate(() => {
      const plansBox = document.querySelector<HTMLButtonElement>('.zoning-nav-button')!.getBoundingClientRect();
      const indicatorsBox = document.querySelector<HTMLButtonElement>('.zoning-nav-button + .zoning-nav-button')!.getBoundingClientRect();
      const rightBox = document.querySelector<HTMLButtonElement>('.navigation-buttons button')!.getBoundingClientRect();
      return { planWidth: plansBox.width, planHeight: plansBox.height, indicatorX: indicatorsBox.x,
        indicatorY: indicatorsBox.y, planX: plansBox.x, planBottom: plansBox.bottom, rightWidth: rightBox.width,
        rightHeight: rightBox.height };
    });
    expect(closed).toBeTruthy();
    expect(sizes.planWidth).toBe(sizes.rightWidth);
    expect(sizes.planHeight).toBe(sizes.rightHeight);
    expect(sizes.indicatorX).toBe(sizes.planX);
    expect(sizes.indicatorY).toBe(sizes.planBottom);

    await search.click();
    const searchPanel = page.getByRole('region', { name: 'Search workspace' });
    await expect(searchPanel).toBeVisible();
    await expect(nav).toHaveAttribute('data-search-open', 'true');
    await expect.poll(async () => {
      const panelBox = await searchPanel.boundingBox();
      const navBox = await nav.boundingBox();
      return !!panelBox && !!navBox && navBox.y >= panelBox.y + panelBox.height + 8;
    }).toBe(true);
    expect((await nav.boundingBox())!.y).toBeGreaterThan(closed!.y);
    await expect(plans).toBeInViewport();
    await expect(indicators).toBeInViewport();
    await page.screenshot({ path: `test-results/zoning-navigation-search-${width}.png` });

    await rightControl.click();
    await expect(searchPanel).toHaveCount(0);
    await expect(nav).toHaveAttribute('data-search-open', 'false');
    await expect.poll(async () => Math.round((await nav.boundingBox())!.y)).toBe(width < 768 ? 76 : 80);
  }
  await page.setViewportSize({ width: 320, height: 900 });
  await plans.click();
  const planPanel = page.getByLabel('Plans panel');
  await expect(planPanel).toBeVisible();
  await expect.poll(async () => {
    const panelBox = await planPanel.boundingBox();
    return !!panelBox && panelBox.x === 0 && panelBox.width < 320 && panelBox.y === 0 && panelBox.height >= 899;
  }).toBe(true);
  await expect(page.getByRole('button', { name: 'Collapse zoning panel' })).toHaveCount(0);
  await page.screenshot({ path: 'test-results/zoning-panel-left-320.png' });
  expect(errors).toEqual([]);
});

test('study-area outlines appear, follow the toggle, and disappear when the active plan is deleted', async ({ page }) => {
  const studyArea = { type: 'Polygon', coordinates: [[[106.76, 10.82], [106.764, 10.82],
    [106.764, 10.824], [106.76, 10.824], [106.76, 10.82]]] };
  const plan = { id: 'fixture-plan', name: 'Fixture plan', revision: 1, area_m2: 1000,
    study_area: studyArea, description: '', horizon: null, status: 'draft', updated_at: new Date().toISOString(),
    baseline: { version: 'fixture', captured_at: new Date().toISOString(), status: 'ready', source: 'Fixture' },
    types: [], scenarios: [{ id: 'existing', name: 'Existing', kind: 'reference', locked: true, zones: [] },
      { id: 'proposal', name: 'Scenario A', kind: 'proposal', locked: false, zones: [] }] };
  let deleted = false;
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: {
    version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#cbdcd7' } }],
  } }));
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [{ id: 'parcels', available: true }] } }));
  await page.route('**/parcels/tiles/**', route => route.fulfill({ status: 204 }));
  await page.route('**/api/v1/zoning/plans**', route => {
    if (route.request().method() === 'DELETE') { deleted = true; return route.fulfill({ status: 204 }); }
    if (route.request().url().endsWith('/fixture-plan')) return route.fulfill({ json: plan });
    return route.fulfill({ json: { plans: deleted ? [] : [plan] } });
  });
  await page.route('**/api/v1/zoning/plans/fixture-plan/land-use', route => route.fulfill({ json: {
    basis: 'observed_parcels', rows: [{ code: 'OTC', parcels: 2, area_m2: 800, category: 'Residential', color: '#D79B8C' }],
  } }));
  await page.goto('/tests/browser/data-layers.html');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await expect(page.getByLabel('Plan details')).toHaveCount(0);
  for (const width of [320, 500, 800, 1000, 1050, 1440]) {
    await page.setViewportSize({ width, height: 700 });
    await expect.poll(() => page.evaluate(() => Math.abs(
      document.querySelector('.zoning-plan-drawer')!.getBoundingClientRect().width -
      document.querySelector('.search-dock')!.getBoundingClientRect().width -
      document.querySelector('.search-dock')!.getBoundingClientRect().left * 2,
    ))).toBeLessThan(1);
  }
  await page.setViewportSize({ width: 1000, height: 700 });
  await page.screenshot({ path: 'test-results/zoning-plans-aligned.png' });
  await page.evaluate(() => window.dataMap.jumpTo({ center: [106.762, 10.821], zoom: 16 }));
  const beforeCreate = await page.evaluate(() => ({ center: window.dataMap.getCenter().toArray(), zoom: window.dataMap.getZoom() }));
  await page.getByRole('button', { name: 'New plan', exact: true }).click();
  await expect.poll(() => page.evaluate(() => ({ center: window.dataMap.getCenter().toArray(), zoom: window.dataMap.getZoom() }))).toEqual(beforeCreate);
  expect(await page.evaluate(() => window.dataMap.getPaintProperty('zoning-vertices', 'circle-stroke-color'))).toBe('#FF6D00');
  const outlines = page.getByRole('checkbox', { name: 'Show parcel outlines', exact: true });
  await expect(outlines).toBeChecked();
  await page.waitForFunction(() => !!window.dataMap.getLayer('zoning-plan-parcels-outline') && window.dataMap.getZoom() >= 12);
  expect(await page.evaluate(() => window.dataMap.getPaintProperty('zoning-plan-parcels-outline', 'line-opacity'))).toBe(.9);
  await page.evaluate(() => window.dataMap.setStyle({ version: 8, sources: {},
    layers: [{ id: 'replacement', type: 'background', paint: { 'background-color': '#d5e4df' } }] }));
  await page.waitForFunction(() => !!window.dataMap.getLayer('zoning-plan-parcels-outline'));
  await outlines.uncheck();
  await expect.poll(() => page.evaluate(() => window.dataMap.getPaintProperty('zoning-plan-parcels-outline', 'line-opacity'))).toBe(0);
  await outlines.check();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.waitForFunction(() => !window.dataMap.getLayer('zoning-plan-parcels-outline'));
  await page.locator('.zoning-plan-list li > button:first-child').click();
  await page.waitForFunction(() => !!window.dataMap.getLayer('zoning-plan-parcels-outline'));
  await expect(page.getByLabel('Plans panel')).toHaveCount(0);
  await expect(page.getByLabel('Plan details')).toBeVisible();
  const widths = await page.evaluate(() => ({ search: document.querySelector('.search-dock')!.getBoundingClientRect().width,
    details: document.querySelector('.zoning-detail-drawer')!.getBoundingClientRect().width }));
  expect(widths.details).toBe(widths.search);
  expect(await page.locator('.zoning-tool-rail button').count()).toBe(6);
  await expect(page.getByRole('button', { name: 'Open time range' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Zoning in scenario' })).toBeVisible();
  await expect(page.getByLabel('Overlap policy')).toBeVisible();
  await page.getByRole('button', { name: 'Existing', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Current parcel land use' })).toContainText('OTC');
  await expect(page.getByLabel('Overlap policy')).toHaveCount(0);
  expect(await page.evaluate(() => !!window.dataMap.getLayer('zoning-plan-parcels-fill'))).toBe(true);
  await page.screenshot({ path: 'test-results/zoning-existing-desktop.png' });
  await page.getByRole('button', { name: 'Scenario A', exact: true }).click();
  await expect(page.getByLabel('Overlap policy')).toHaveValue('preserve');
  await page.getByRole('button', { name: 'Development' }).click();
  await expect(page.getByLabel('Plan details')).toContainText('Select a parcel on the map.');
  await page.getByRole('button', { name: 'Zoning', exact: true }).click();
  const scenarioBox = await page.locator('.zoning-scenario-bar').boundingBox();
  const navigationBox = await page.locator('.navigation-cluster').boundingBox();
  expect(scenarioBox!.x + scenarioBox!.width).toBeLessThanOrEqual(navigationBox!.x);
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await expect(page.getByLabel('Plans panel')).toBeVisible();
  await expect(page.getByLabel('Plan details')).toHaveCount(0);
  await page.locator('.zoning-plan-list li > button:first-child').click();
  await expect(page.getByLabel('Plan details')).toBeVisible();
  await page.screenshot({ path: 'test-results/zoning-panel-right-desktop.png' });
  await page.setViewportSize({ width: 320, height: 900 });
  await page.screenshot({ path: 'test-results/zoning-panel-right-plan-320.png' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1000, height: 700 });
  await page.getByRole('button', { name: 'Zoning', exact: true }).click();
  await page.getByRole('button', { name: 'Add zoning type' }).click();
  const editor = page.getByRole('dialog', { name: 'New zoning type' });
  await editor.getByLabel('Code', { exact: true }).click();
  const catalog = editor.getByRole('region', { name: 'Zoning code catalog' });
  await expect(catalog.getByRole('button', { name: /^RES Residential/ })).toBeVisible();
  await catalog.getByRole('button', { name: /^RES Residential/ }).click();
  await expect(editor.getByLabel('Code', { exact: true })).toHaveValue('RES');
  await expect(editor.getByLabel('Name', { exact: true })).toHaveValue('Residential / Khu ở');
  await expect(editor.getByRole('region', { name: 'Planning rule guidance' })).toContainText('Table 2.8');
  await expect(editor.getByLabel('Coverage (%)')).toHaveValue('');
  await editor.getByLabel('Code', { exact: true }).fill('ODT');
  await catalog.getByRole('button', { name: /^ODT Đất ở tại đô thị/ }).click();
  await expect(editor.getByLabel('Description')).toContainText('Đất dùng làm nhà ở');
  await expect(editor.getByRole('region', { name: 'Planning rule guidance' })).toContainText('Land use ≠ zoning rules');
  await expect(editor.getByLabel('Source / design basis')).toContainText('not an approved zoning rule');
  await editor.getByRole('button', { name: 'Cancel' }).click();
  await page.getByRole('button', { name: 'Plan info' }).click();
  await expect(page.getByLabel('Plan details')).toContainText('Planning horizon');
  for (const action of ['Rename', 'Locate', 'Edit study area']) await expect(page.getByRole('button', { name: action, exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Delete plan', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click();
  await page.waitForFunction(() => !window.dataMap.getLayer('zoning-plan-parcels-outline') && !window.dataMap.getSource('zoning-plan-parcels'));
  expect(deleted).toBe(true);
});

test('study-area drawing snaps to a visible road and Ctrl temporarily disables it', async ({ page }) => {
  let created: { study_area: { coordinates: number[][][] } } | null = null;
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: {
    version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#cbdcd7' } }],
  } }));
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [] } }));
  await page.route('**/api/v1/zoning/plans', route => {
    if (route.request().method() === 'POST') {
      created = route.request().postDataJSON();
      return route.fulfill({ status: 422, json: { detail: 'Captured drawing' } });
    }
    return route.fulfill({ json: { plans: [] } });
  });
  await page.goto('/tests/browser/data-layers.html');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.getByRole('button', { name: 'New plan', exact: true }).click();
  await page.evaluate(() => {
    const map = (window as unknown as { dataMap: import('maplibre-gl').Map }).dataMap;
    map.jumpTo({ center: [106.762, 10.822], zoom: 16 });
    map.addSource('test-roads', { type: 'geojson', data: { type: 'Feature', properties: {},
      geometry: { type: 'LineString', coordinates: [[106.76, 10.821], [106.766, 10.821]] } } });
    map.addLayer({ id: 'road-centerline-test', source: 'test-roads', type: 'line', paint: { 'line-width': 2 } });
  });
  await page.waitForTimeout(500);
  const hitCount = await page.evaluate(() => {
    const map = (window as unknown as { dataMap: import('maplibre-gl').Map }).dataMap;
    const point = map.project([106.762, 10.82103]);
    return map.queryRenderedFeatures([[point.x - 10, point.y - 10], [point.x + 10, point.y + 10]],
      { layers: ['road-centerline-test'] }).length;
  });
  expect(hitCount).toBeGreaterThan(0);
  await page.getByLabel('Plan name', { exact: true }).fill('Snap test');
  const click = async (coordinates: [number, number]) => {
    const point = await page.evaluate(p => (window as unknown as { dataMap: import('maplibre-gl').Map }).dataMap.project(p), coordinates);
    await page.mouse.click(point.x, point.y);
  };
  await click([106.762, 10.82103]);
  await page.keyboard.down('Control');
  await click([106.763, 10.82103]);
  await page.keyboard.up('Control');
  await click([106.764, 10.824]);
  await click([106.760, 10.824]);
  await page.getByRole('button', { name: 'Create plan' }).click();
  await expect.poll(() => created).not.toBeNull();
  const ring = created!.study_area.coordinates[0];
  expect(ring[0][1]).toBeCloseTo(10.821, 5);
  expect(ring[1][1]).toBeCloseTo(10.82103, 5);
});
