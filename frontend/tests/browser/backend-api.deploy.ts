import { expect, test } from '@playwright/test';

test(
  'browser loads the frontend and fetches population data through its same-origin API',
  async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle('Vietnam Urban Data Explorer');

    const catalog = await page.evaluate(async () => {
      const response = await fetch('/api/v1/population');
      if (!response.ok) throw new Error(`Population API returned ${response.status}`);
      return response.json();
    });
    expect(catalog.available).toBeTruthy();
    expect(catalog.years.length).toBe(16);
  },
);

test('frontend proxy exposes the ready backend and API discovery document', async ({ request }) => {
  const health = await request.get('/health');
  expect(health.ok()).toBeTruthy();
  expect(await health.json()).toEqual({ status: 'ok' });

  const ready = await request.get('/ready');
  expect(ready.ok()).toBeTruthy();
  expect((await ready.json()).status).toBe('ready');

  const index = await request.get('/api/v1');
  expect(index.ok()).toBeTruthy();
  expect((await index.json()).endpoints.population).toBe('/api/v1/population');

  const openapi = await request.get('/api/v1/openapi.json');
  expect(openapi.ok()).toBeTruthy();
  const paths = (await openapi.json()).paths;
  expect(paths['/api/v1/population/{year}/tiles/{z}/{x}/{y}.png']).toBeDefined();
});

test('population catalog, sample query and map tile serve loaded raster data', async ({ request }) => {
  const response = await request.get('/api/v1/population');
  expect(response.ok()).toBeTruthy();
  const catalog = await response.json();
  expect(catalog.available).toBeTruthy();
  expect(catalog.years.length).toBeGreaterThan(0);
  expect(catalog.crs).toBe('EPSG:4326');

  const year = catalog.years.at(-1).year as number;
  const sample = await request.get(
    `/api/v1/population/${year}/value?lng=106.7&lat=10.8`,
  );
  expect(sample.ok()).toBeTruthy();
  const sampled = await sample.json();
  expect(sampled.year).toBe(year);
  expect(sampled.nodata).toBeFalsy();
  expect(typeof sampled.population).toBe('number');

  const tilejson = await request.get(`/api/v1/population/${year}/tilejson.json`);
  expect(tilejson.ok()).toBeTruthy();
  expect((await tilejson.json()).format).toBe('png');

  const zoom = 10;
  const longitude = 106.7;
  const latitude = (10.8 * Math.PI) / 180;
  const x = Math.floor(((longitude + 180) / 360) * 2 ** zoom);
  const y = Math.floor(
    ((1 - Math.asinh(Math.tan(latitude)) / Math.PI) / 2) * 2 ** zoom,
  );
  const tile = await request.get(`/api/v1/population/${year}/tiles/${zoom}/${x}/${y}.png`);
  expect(tile.status()).toBe(200);
  expect(tile.headers()['content-type']).toContain('image/png');
  expect((await tile.body()).subarray(0, 8)).toEqual(
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
  );
});

test('vector layer catalog responds with ETL layer contracts', async ({ request }) => {
  const response = await request.get('/api/v1/layers');
  expect(response.ok()).toBeTruthy();
  const catalog = await response.json();
  const ids = catalog.layers.map((layer: { id: string }) => layer.id);
  expect(ids).toContain('flood_history');
  expect(ids).toContain('flood_risk');
  expect(ids).toContain('land_price');
});

test('flood history, satellite classification and risk queries return loaded features', async ({ request }) => {
  for (const layer of ['history', 'satellite', 'risk']) {
    const response = await request.get(`/api/v1/floods/${layer}`);
    expect(response.ok(), `${layer} endpoint should be available`).toBeTruthy();
    const collection = await response.json();
    expect(collection.type).toBe('FeatureCollection');
    expect(collection.features.length, `${layer} should contain loaded features`).toBeGreaterThan(0);
  }
});
