import { expect, test } from '@playwright/test';

test('3D mode keeps Goong buildings visible alongside streamed models', async ({ page }) => {
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: {
    version: 8,
    sources: { composite: { type: 'vector', tiles: ['http://127.0.0.1:5173/fake-building-tile/{z}/{x}/{y}.pbf'] } },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': '#cbdcd7' } },
      { id: 'goong-building', type: 'fill-extrusion', source: 'composite', 'source-layer': 'VN_Building',
        minzoom: 14, layout: { visibility: 'none' },
        paint: { 'fill-extrusion-color': '#aaa', 'fill-extrusion-height': 12 } },
    ],
  } }));
  await page.route('**/fake-building-tile/**', route => route.fulfill({ status: 204 }));
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [
    { id: 'synthetic_buildings', available: true },
  ] } }));
  await page.route('**/api/v1/layers/synthetic_buildings/features**', route => route.fulfill({ json: {
    type: 'FeatureCollection', features: [], metadata: {},
  } }));
  await page.route('**/api/v1/layers/synthetic_buildings/tiles/**', route => route.fulfill({ status: 204 }));

  await page.goto('/tests/browser/data-layers.html');
  await page.waitForFunction(() => !!window.dataMap?.getLayer('goong-building'));
  await page.getByRole('button', { name: 'Switch to 3D' }).click();
  await page.waitForFunction(() => !!window.dataMap.getLayer('dataset-synthetic-buildings'));
  expect(await page.evaluate(() => ({
    goong: window.dataMap.getLayoutProperty('goong-building', 'visibility'),
    generated: window.dataMap.getLayer('dataset-synthetic-buildings')?.source,
  }))).toEqual({ goong: 'visible', generated: 'dataset-synthetic-buildings' });
});
