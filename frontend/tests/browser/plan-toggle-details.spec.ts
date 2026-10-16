import { expect, test } from '@playwright/test';
import { GeoJSONVT } from '@maplibre/geojson-vt';
import { fromGeojsonVt } from '@maplibre/vt-pbf';

test('showing a plan previews its parcels, zoning and buildings without opening the editor', async ({ page }) => {
  const study = { type: 'Polygon', coordinates: [[[106.76, 10.82], [106.764, 10.82],
    [106.764, 10.824], [106.76, 10.824], [106.76, 10.82]]] };
  const building = { id: 'building-1', geometry: { type: 'Polygon', coordinates: [[[106.761, 10.821],
    [106.762, 10.821], [106.762, 10.822], [106.761, 10.822], [106.761, 10.821]]] },
  color: '#ff6d00', height_m: 18, floor_stack: [] };
  const plan = { id: 'preview-plan', name: 'Preview plan', revision: 1, area_m2: 1000, study_area: study,
    description: '', horizon: null, status: 'draft', updated_at: new Date().toISOString(),
    baseline: { version: 'fixture', captured_at: new Date().toISOString(), status: 'ready', source: 'Fixture' },
    types: [{ id: 'type-1', code: 'MU', color: '#ff6d00' }],
    scenarios: [{ id: 'existing', name: 'Existing', kind: 'reference', locked: true, zones: [] },
      { id: 'proposal', name: 'Scenario A', kind: 'proposal', locked: false,
        zones: [{ id: 'zone-1', type_id: 'type-1', geometry: study }], buildings: [building] }] };
  const parcels = new GeoJSONVT({ type: 'FeatureCollection', features: [{ type: 'Feature',
    properties: { parcel_id: 'parcel-1', color: '#D79B8C' }, geometry: study }] }, { maxZoom: 18 });
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: {
    version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#cbdcd7' } }],
  } }));
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [{ id: 'parcels', available: true }] } }));
  await page.route('**/parcels/tiles/**', route => {
    const match = route.request().url().match(/\/(\d+)\/(\d+)\/(\d+)\.pbf/)!;
    const tile = parcels.getTile(+match[1], +match[2], +match[3]);
    return tile ? route.fulfill({ contentType: 'application/vnd.mapbox-vector-tile',
      body: Buffer.from(fromGeojsonVt({ features: tile })) }) : route.fulfill({ status: 204 });
  });
  await page.route('**/api/v1/zoning/plans**', route => route.request().url().includes('.pbf') ? route.fallback()
    : route.fulfill({ json: route.request().url().endsWith('/preview-plan') ? plan : { plans: [plan] } }));
  await page.goto('/tests/browser/data-layers.html');
  await page.getByRole('button', { name: 'Plans', exact: true }).click();
  await page.evaluate(() => window.dataMap.jumpTo({ center: [106.762, 10.822], zoom: 16 }));
  await page.getByRole('button', { name: 'Show plan Preview plan on map' }).click();
  await expect(page.getByLabel('Plans panel')).toBeVisible();
  await expect(page.getByLabel('Plan details')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => ({
    parcelLayer: !!window.dataMap.getLayer('zoning-preview-parcels-preview-plan-fill'),
    zone: window.dataMap.querySourceFeatures('zoning-editor').some(f => f.properties.kind === 'plan-zone-preview'),
    building: window.dataMap.querySourceFeatures('development-scene').some(f => f.properties.kind === 'building'),
  }))).toEqual({ parcelLayer: true, zone: true, building: true });
  await expect.poll(() => page.evaluate(() => window.dataMap.queryRenderedFeatures({
    layers: ['zoning-preview-parcels-preview-plan-fill'],
  }).some(feature => feature.properties.color === '#D79B8C'))).toBe(true);
  await page.getByRole('button', { name: 'Hide plan Preview plan on map' }).click();
  await expect.poll(() => page.evaluate(() => ({
    parcelLayer: !!window.dataMap.getLayer('zoning-preview-parcels-preview-plan-fill'),
    zone: window.dataMap.querySourceFeatures('zoning-editor').some(f => f.properties.kind === 'plan-zone-preview'),
    building: window.dataMap.querySourceFeatures('development-scene').some(f => f.properties.kind === 'building'),
  }))).toEqual({ parcelLayer: false, zone: false, building: false });
});
