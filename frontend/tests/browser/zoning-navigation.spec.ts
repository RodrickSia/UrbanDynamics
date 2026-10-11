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
    return !!panelBox && panelBox.x === 0 && panelBox.y === 0 && panelBox.height >= 899;
  }).toBe(true);
  expect(errors).toEqual([]);
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
