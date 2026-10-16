import { expect, test } from '@playwright/test';
import { GeoJSONVT } from '@maplibre/geojson-vt';
import { fromGeojsonVt } from '@maplibre/vt-pbf';

test('historical traffic roads snap to the pointer and reveal their estimate on hover', async ({ page }, testInfo) => {
  const roads = new GeoJSONVT({
    type: 'Feature',
    properties: {
      road: 'Fixture road', predicted_los: 'D', congestion_score: 73,
      prediction_basis: 'direct_observation', confidence: 'high',
    },
    geometry: { type: 'LineString', coordinates: [[106.69, 10.8], [106.71, 10.8]] },
  }, { maxZoom: 18 });
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: {
    version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#dbe5e4' } }],
  } }));
  await page.route('**/api/v1/**', route => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/v1/layers') return route.fulfill({ json: { layers: [] } });
    if (pathname === '/api/v1/population') return route.fulfill({ json: { available: false, years: [] } });
    if (pathname === '/api/v1/traffic/catalog') return route.fulfill({ json: { available: true, network_available: false } });
    if (pathname === '/api/v1/traffic/sumo-simulations/catalog') return route.fulfill({ json: { available: false } });
    if (pathname === '/api/v1/traffic/prediction') return route.fulfill({ json: {
      type: 'FeatureCollection', features: [{ properties: { road: 'Fixture road' } }], metadata: {},
    } });
    if (pathname.includes('/api/v1/traffic/prediction/tiles/')) {
      const [z, x, y] = pathname.match(/tiles\/(\d+)\/(\d+)\/(\d+)/)!.slice(1).map(Number);
      return route.fulfill({ contentType: 'application/vnd.mapbox-vector-tile',
        body: Buffer.from(fromGeojsonVt({ features: roads.getTile(z, x, y) ?? { features: [] } })) });
    }
    return route.fulfill({ status: 404 });
  });
  await page.goto('/tests/browser/data-layers.html');
  await page.waitForFunction('window.dataMap?.isStyleLoaded()');
  await page.evaluate(() => window.dataMap.jumpTo({ center: [106.7, 10.8], zoom: 14 }));
  await page.getByRole('button', { name: 'Open data layers' }).click();
  const layer = page.getByRole('checkbox', { name: 'Traffic congestion prediction (historical)' });
  await expect(layer).toBeEnabled();
  await layer.check();
  await expect(page.getByRole('button', { name: 'Apply' })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('traffic-controls.png') });
  await page.getByRole('region', { name: 'Data layers' }).getByRole('button', { name: 'Close data layers' }).click();
  await expect.poll(() => page.evaluate(() => window.dataMap.queryRenderedFeatures({ layers: ['dataset-traffic'] }).length))
    .toBeGreaterThan(0);
  const point = await page.evaluate(() => window.dataMap.project([106.7, 10.8]));
  await page.mouse.move(point.x, point.y + 8);
  const tooltip = page.getByRole('tooltip', { name: 'Historical congestion road details' });
  await expect(tooltip).toContainText('Fixture road');
  await expect(tooltip).toContainText('73');
  await expect(tooltip).toContainText('direct observation');
  await expect(page.locator('.dataset-line-anchor')).toHaveCount(1);
  await expect.poll(() => tooltip.evaluate(element => getComputedStyle(element).opacity)).toBe('1');
  await page.screenshot({ path: testInfo.outputPath('traffic-hover.png') });
  await page.mouse.move(point.x, point.y + 30);
  await expect(tooltip).toHaveCount(0);
});
