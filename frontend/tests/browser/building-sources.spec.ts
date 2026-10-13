import { expect, test } from '@playwright/test';

test('main building sources show in 3D and disappear in 2D, including style reload', async ({ page }) => {
  const style = {
    version: 8,
    sources: { composite: { type: 'vector', tiles: ['http://127.0.0.1:5173/fake-building-tile/{z}/{x}/{y}.pbf'] } },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': '#cbdcd7' } },
      { id: 'goong-building', type: 'fill-extrusion', source: 'composite', 'source-layer': 'VN_Building',
        minzoom: 14,
        paint: { 'fill-extrusion-color': '#aaa', 'fill-extrusion-height': 12 } },
    ],
  };
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: style }));
  await page.route('https://tiles.mapterhorn.com/**', route => route.abort());
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
  expect(await page.evaluate(() => window.dataMap.getLayoutProperty('goong-building', 'visibility'))).toBe('none');
  await page.getByRole('button', { name: 'Switch to 3D' }).click();
  await page.waitForFunction(() => !!window.dataMap.getLayer('dataset-synthetic-buildings'));
  expect(await page.evaluate(() => ({
    goong: window.dataMap.getLayer('urban-buildings-3d')?.source,
    generated: window.dataMap.getLayer('dataset-synthetic-buildings')?.source,
  }))).toEqual({ goong: 'composite', generated: 'dataset-synthetic-buildings' });
  await page.getByRole('button', { name: 'Switch to 2D' }).click();
  await page.waitForFunction(() => window.dataMap.getPitch() === 0 && !window.dataMap.isMoving());
  const extrusions = () => page.evaluate(() => window.dataMap.getStyle().layers.filter(layer =>
    layer.type === 'fill-extrusion' && layer.layout?.visibility !== 'none').map(layer => layer.id));
  expect(await extrusions()).toEqual([]);
  await page.evaluate(value => window.dataMap.setStyle(value as Parameters<typeof window.dataMap.setStyle>[0]), style);
  await page.waitForFunction(() => window.dataMap.isStyleLoaded());
  expect(await extrusions()).toEqual([]);
  await page.getByRole('button', { name: 'Switch to 3D' }).click();
  await expect.poll(extrusions).toEqual(expect.arrayContaining(['urban-buildings-3d', 'dataset-synthetic-buildings']));
});
