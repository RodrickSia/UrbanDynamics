import { expect, test } from '@playwright/test';
import { GeoJSONVT } from '@maplibre/geojson-vt';
import { fromGeojsonVt } from '@maplibre/vt-pbf';

const rect = (w: number, s: number, e: number, n: number) => ({ type: 'Polygon' as const, coordinates: [[[w,s],[e,s],[e,n],[w,n],[w,s]]] });
const study = rect(106.760,10.820,106.764,10.824);
test('plan colors and both building providers stay within the study area and restore after exit', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));

  const buildings = new GeoJSONVT({ type: 'FeatureCollection', features: [
    { type: 'Feature', id: 1, properties: { height: 18, height_m: 18 }, geometry: rect(106.761,10.821,106.7615,10.8215) },
    { type: 'Feature', id: 2, properties: { height: 12, height_m: 12 }, geometry: rect(106.7637,10.822,106.7645,10.8225) },
    { type: 'Feature', id: 3, properties: { height: 20, height_m: 20 }, geometry: rect(106.765,10.821,106.7655,10.8215) },
  ] }, { maxZoom: 18 });
  const parcels = new GeoJSONVT({ type: 'FeatureCollection', features: [
    { type: 'Feature', properties: { parcel_id: '1', mdsdd: 'ODT', color: '#D79B8C' }, geometry: rect(106.760,10.820,106.762,10.824) },
    { type: 'Feature', properties: { parcel_id: '2', mdsdd: 'TMD', color: '#C18EAD' }, geometry: rect(106.762,10.820,106.764,10.824) },
  ] }, { maxZoom: 18 });
  const style = { version: 8, sources: { composite: { type: 'vector', tiles: ['http://127.0.0.1:5173/goong-fixture/{z}/{x}/{y}.pbf'] } }, layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#e5ebe8' } },
    { id: 'goong-native', source: 'composite', 'source-layer': 'VN_Building', type: 'fill-extrusion', paint: { 'fill-extrusion-height': 12 } },
  ] };
  const plan = { id: 'plan-scope-fixture', name: 'Plan colors', revision: 1, area_m2: 190000, study_area: study,
    description: '', horizon: null, status: 'draft', updated_at: new Date().toISOString(),
    baseline: { version: 'fixture', captured_at: new Date().toISOString(), status: 'ready', source: 'Fixture' },
    types: [{ id: 'zone-type', code: 'MU', name: 'Mixed use', color: '#FF6D00', description: '', uses: '',
      max_height: null, max_floors: null, coverage: null, far: null, setback_front: null, setback_side: null, setback_rear: null,
      source: '', version: 1, status: 'proposal' }],
    scenarios: [{ id: 'existing', name: 'Existing', kind: 'reference', locked: true, zones: [] },
      { id: 'proposal', name: 'Scenario A', kind: 'proposal', locked: false,
        zones: [{ id: 'zone', type_id: 'zone-type', geometry: rect(106.761,10.8205,106.763,10.822), area_m2: 40000 }] }] };
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: style }));
  await page.route('https://tiles.mapterhorn.com/**', route => route.abort());
  await page.route('**/*.pbf*', route => {
    const url = route.request().url(), match = url.match(/\/(\d+)\/(\d+)\/(\d+)\.pbf/)!;
    const tile = (url.includes('/parcels/') ? parcels : buildings).getTile(+match[1], +match[2], +match[3]);
    const layer = url.includes('goong-fixture') ? 'VN_Building' : 'features';
    return tile ? route.fulfill({ contentType: 'application/vnd.mapbox-vector-tile', body: Buffer.from(fromGeojsonVt({ [layer]: tile })) }) : route.fulfill({ status: 204 });
  });
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [{ id: 'parcels', available: true }, { id: 'synthetic_buildings', available: true }] } }));
  await page.route('**/api/v1/layers/*/features**', route => route.fulfill({ json: { type: 'FeatureCollection', features: [] } }));
  await page.route('**/api/v1/zoning/plans**', route => route.request().url().includes('.pbf') ? route.fallback()
    : route.fulfill({ json: route.request().url().endsWith('/plan-scope-fixture') ? plan : { plans: [plan], rows: [] } }));
  await page.goto('/tests/browser/data-layers.html');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.locator('.zoning-plan-list .zoning-plan-open').click();
  expect(errors).toEqual([]);
  await expect.poll(() => page.evaluate(() => ({ loaded: window.dataMap.isStyleLoaded(), moving: window.dataMap.isMoving(),
    pending: Object.keys(window.dataMap.getStyle()?.sources ?? {}).filter(id => !window.dataMap.isSourceLoaded(id)) }))).toEqual({ loaded: true, moving: false, pending: [] });
  await expect.poll(() => page.evaluate(() => [...new Set(window.dataMap.queryRenderedFeatures({ layers: ['zoning-plan-parcels-fill'] }).map(f => f.properties.color))].sort())).toEqual(['#C18EAD','#D79B8C']);
  await page.getByRole('button', { name: 'Existing', exact: true }).click();
  expect(await page.evaluate(() => window.dataMap.getPaintProperty('zoning-plan-parcels-fill', 'fill-opacity'))).toBe(.35);
  await page.getByRole('button', { name: 'Scenario A', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.dataMap.querySourceFeatures('zoning-editor').find(f => f.properties.kind === 'zone')?.properties.color)).toBe('#FF6D00');
  await page.getByRole('button', { name: 'Switch to 3D' }).click();

  const scoped = ['plan-scope-urban-buildings-3d', 'plan-scope-dataset-synthetic-buildings'];
  for (const source of scoped) {
    await expect.poll(() => page.evaluate(id => [...new Set(window.dataMap.querySourceFeatures(id).map(f => f.id))].sort(), source)).toEqual([1,2]);
    expect(await page.evaluate(id => window.dataMap.querySourceFeatures(id).every(f => {
      const coords = f.geometry.type === 'Polygon' ? f.geometry.coordinates.flat() : f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates.flat(2) : [];
      return coords.every(p => p[0] <= 106.76401 && p[0] >= 106.75999 && p[1] <= 10.82401 && p[1] >= 10.81999);
    }), source)).toBe(true);
  }
  await page.screenshot({ path: '../.runtime/development/plan-colors-scoped-3d.png' });
  await page.getByRole('button', { name: 'Switch to 2D' }).click();
  await expect.poll(() => page.evaluate(() => window.dataMap.getStyle().layers.filter(l => l.type === 'fill-extrusion' && l.layout?.visibility !== 'none' && window.dataMap.getPaintProperty(l.id,'fill-extrusion-opacity') !== 0).map(l => l.id))).toEqual([]);
  await page.getByRole('button', { name: 'Switch to 3D' }).click();
  for (const source of scoped) await expect.poll(() => page.evaluate(id =>
    [...new Set(window.dataMap.queryRenderedFeatures({ layers: [id] }).map(f => f.id))].sort(), source)).toEqual([1,2]);
  await page.evaluate(value => window.dataMap.setStyle(value as Parameters<typeof window.dataMap.setStyle>[0]), style);
  await expect.poll(() => page.evaluate(() => !!window.dataMap.getLayer('plan-scope-urban-buildings-3d'))).toBe(true);
  for (const source of scoped) await expect.poll(() => page.evaluate(id => window.dataMap.getLayer(id)
    ? [...new Set(window.dataMap.queryRenderedFeatures({ layers: [id] }).map(f => f.id))].sort() : [], source)).toEqual([1,2]);
  await page.getByRole('button', { name: 'Close plan', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.dataMap.getPaintProperty('urban-buildings-3d','fill-extrusion-opacity'))).toBe(.8);
  expect(await page.evaluate(() => window.dataMap.getLayer('plan-scope-urban-buildings-3d'))).toBeUndefined();
  expect(errors).toEqual([]);
});
