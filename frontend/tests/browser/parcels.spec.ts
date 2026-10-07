import { expect, test } from '@playwright/test';
import { GeoJSONVT } from '@maplibre/geojson-vt';
import { fromGeojsonVt } from '@maplibre/vt-pbf';

test('parcel colors, distant tiles, accessible details and style restoration', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const requests: string[] = [];
  let failDetail = true;
  let missingPrice = false;
  const plots = new GeoJSONVT({ type: 'Feature', id: 42,
    properties: { parcel_id: '42', mdsdd: 'ODT', color: '#d6604d' },
    geometry: { type: 'Polygon', coordinates: [[[106.699,10.799], [106.701,10.799],
      [106.701,10.801], [106.699,10.801], [106.699,10.799]]] } }, { maxZoom: 16 });
  const detail = { parcel: { id: 42, uniq_id: 'sample', to_ban_do: '142', thua: '14',
    area_m2: 192.33, phuong: 'Tân Sơn', tinh: 'TP. Hồ Chí Minh' },
    land_use: { code: 'ODT', color: '#d6604d', label: null, color_source: 'source_sample' },
    area_source: 'map_geometry', planning: [{ label: 'Đất ở', area_m2: 180.9 }],
    price: { status: 'reference', unit_price_vnd_m2: 10000000, estimated_land_total_vnd: 1923300000,
      price_category: 'Residential', normalized_land_use: 'Residential land', classification_confidence: 'high',
      road_match_status: 'spatially_checked', geometry_review_status: 'reviewed',
      candidates: [], selected: { feature_id: 'road', distance_m: 5,
        properties: { road: 'Example road', source_url: 'https://example.org/source.pdf' } } } };
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: { version: 8, sources: {},
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#dbe5e4' } }] } }));
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url());
    requests.push(url.pathname + url.search);
    if (url.pathname === '/api/v1/layers') return route.fulfill({ json: { layers: [{ id: 'parcels', available: true }] } });
    if (url.pathname === '/api/v1/parcels/42') return route.fulfill({ status: failDetail ? 503 : 200,
      json: missingPrice ? { ...detail, price: { ...detail.price, status: 'unavailable',
        unit_price_vnd_m2: null, estimated_land_total_vnd: null, selected: null } } : detail });
    if (url.pathname.endsWith('/features')) return route.fulfill({ json: { type: 'FeatureCollection', features: [], metadata: {} } });
    if (url.pathname.endsWith('.pbf')) {
      const [z,x,y] = url.pathname.match(/tiles\/(\d+)\/(\d+)\/(\d+)/)!.slice(1).map(Number);
      return route.fulfill({ contentType: 'application/vnd.mapbox-vector-tile',
        body: Buffer.from(fromGeojsonVt({ features: plots.getTile(z,x,y) ?? { features: [] } })) });
    }
    return route.fulfill({ status: 404 });
  });
  await page.goto('/tests/browser/data-layers.html');
  await page.waitForFunction('window.dataMap?.isStyleLoaded()');
  await page.evaluate('window.dataMap.jumpTo({center:[106.7,10.8],zoom:12})');
  await page.getByRole('button', { name: 'Open data layers', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Land parcels', exact: true }).check();
  await page.waitForFunction('window.dataMap.getLayer("dataset-parcels-outline") && window.dataMap.queryRenderedFeatures({layers:["dataset-parcels"]}).length > 0');
  expect(requests.some(url => url.includes('/parcels/tiles/12/') && url.includes('schema=2'))).toBe(true);
  expect(await page.evaluate('window.dataMap.queryRenderedFeatures({layers:["dataset-parcels"]})[0].properties.color')).toBe('#d6604d');
  await page.getByRole('region', { name: 'Data layers' }).getByRole('button', { name: 'Close data layers' }).click();
  await page.evaluate('window.dataMap.jumpTo({center:[106.7,10.8],zoom:16})');
  await page.waitForFunction('window.dataMap.isStyleLoaded()');
  await page.mouse.click(500, 350);
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('Plot details could not be loaded');
  failDetail = false;
  await dialog.getByRole('button', { name: 'Try again' }).click();
  await expect(dialog).toHaveAccessibleName('Sheet 142 · Plot 14');
  await expect(dialog).toContainText('1.923.300.000');
  await expect(dialog).toContainText('10.000.000');
  await expect(dialog).toContainText('Estimated Land Value');
  await expect(dialog).toContainText(/192,33 m².*10\.000\.000 ₫\/m².*1\.923\.300\.000 ₫/);
  await expect(dialog).not.toContainText('Source parcel geometry');
  await expect(dialog).not.toContainText('Source ID');
  await expect(dialog).not.toContainText('Area calculated from mapped geometry');
  await expect(dialog).toContainText('Đất ở');
  const bounds = (await dialog.boundingBox())!;
  expect(Math.abs(bounds.x + bounds.width / 2 - 500)).toBeLessThan(2);
  await page.screenshot({ path: testInfo.outputPath('parcel-details-desktop.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect.poll(async () => (await dialog.boundingBox())!.width).toBeLessThan(391);
  await page.screenshot({ path: testInfo.outputPath('parcel-details-mobile.png') });
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  missingPrice = true;
  await page.setViewportSize({ width: 1000, height: 700 });
  await page.evaluate('window.dataMap.jumpTo({center:[106.7,10.8],zoom:16})');
  await page.mouse.click(500, 350);
  await expect(dialog).toContainText('Estimated Land Value');
  await expect(dialog.locator('.parcel-price')).toHaveText('null');
  await expect(dialog.locator('.parcel-formula')).toContainText('null');
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await page.evaluate('window.dataMap.setStyle({version:8,sources:{},layers:[]})');
  await page.waitForFunction('window.dataMap.getLayer("dataset-parcels-outline") && window.dataMap.getLayer("dataset-parcels")');
  await page.getByRole('button', { name: 'Open data layers', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Land parcels', exact: true }).uncheck();
  await expect.poll(() => page.evaluate('Boolean(window.dataMap.getSource("dataset-parcels"))')).toBe(false);
  expect(errors).toEqual([]);
});
