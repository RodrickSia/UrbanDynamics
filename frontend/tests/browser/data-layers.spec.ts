import { expect, test } from '@playwright/test';
import { GeoJSONVT } from '@maplibre/geojson-vt';
import { fromGeojsonVt } from '@maplibre/vt-pbf';

test('published datasets render, filter, inspect and survive style swaps without breaking measurement', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const tiles = new GeoJSONVT(
    {
      type: 'Feature',
      properties: {
        location: 'Cầu Ông Dầu',
        reported_ward: 'Phường Hiệp Bình Phước',
        reported_district: 'Thủ Đức',
        current_admin_unit: 'Phường Hiệp Bình',
        geocoding_method: 'Area point',
        spatial_precision: 'Low',
        observed_at: '2019-04-09',
        depth_max_cm: 40,
      },
      geometry: { type: 'Point', coordinates: [106.7, 10.8] },
    },
    { maxZoom: 18 },
  );
  const areas = new GeoJSONVT(
    {
      type: 'Feature',
      properties: { status: 'rain_alert_near_historical_flood' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [106.69, 10.79],
            [106.71, 10.79],
            [106.71, 10.81],
            [106.69, 10.81],
            [106.69, 10.79],
          ],
        ],
      },
    },
    { maxZoom: 18 },
  );
  const roads = new GeoJSONVT(
    {
      type: 'Feature',
      properties: {
        geometry_reviewed: false,
        publication_match_mode: 'automatic',
        geometry_coverage: 'whole_named_road_proxy',
        road: 'Published fixture road',
        residential_vnd_m2: 5000000,
      },
      geometry: {
        type: 'LineString',
        coordinates: [
          [106.69, 10.8],
          [106.71, 10.8],
        ],
      },
    },
    { maxZoom: 18 },
  );
  let empty = false,
    fail = false,
    prices = false;
  const queries: string[] = [];
  await page.route('https://tiles.goong.io/**', (route) =>
    route.fulfill({
      json: {
        version: 8,
        sources: {},
        layers: [
          { id: 'background', type: 'background', paint: { 'background-color': '#dbe5e4' } },
        ],
      },
    }),
  );
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 256;
    const context = canvas.getContext('2d')!;
    context.fillStyle = '#fecc5c';
    context.fillRect(0, 0, 256, 256);
    return canvas.toDataURL().split(',')[1];
  });
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    queries.push(url.pathname + url.search);
    if (url.pathname === '/api/v1/layers')
      return route.fulfill({
        json: {
          layers: [
            { id: 'flood_history', available: true },
            { id: 'flood_risk', available: true },
            { id: 'flood_satellite', available: true },
            { id: 'land_price', available: true },
          ],
        },
      });
    if (url.pathname === '/api/v1/population')
      return route.fulfill({ json: { available: true, years: [{ year: 2022 }, { year: 2024 }] } });
    if (url.pathname.endsWith('/features'))
      return route.fulfill({
        status: fail ? 503 : 200,
        json: {
          type: 'FeatureCollection',
          features:
            empty || (url.pathname.includes('land_price') && !prices)
              ? []
              : [
                  {
                    properties: {
                      location: 'Fixture observation',
                      geometry_reviewed: false,
                      publication_match_mode: 'automatic',
                      geometry_coverage: 'whole_named_road_proxy',
                    },
                  },
                ],
          metadata: {},
        },
      });
    if (url.pathname.endsWith('/stats'))
      return route.fulfill({
        status: empty ? 404 : 200,
        json: { statistics: { pixel_count: 10 } },
      });
    if (url.pathname.endsWith('/value')) return route.fulfill({ json: { population: 42.5 } });
    if (url.pathname.endsWith('.png'))
      return empty
        ? route.fulfill({ status: 204 })
        : route.fulfill({ contentType: 'image/png', body: Buffer.from(png, 'base64') });
    if (url.pathname.endsWith('.pbf')) {
      const [z, x, y] = url.pathname
        .match(/tiles\/(\d+)\/(\d+)\/(\d+)/)!
        .slice(1)
        .map(Number);
      const source = url.pathname.includes('flood_history')
        ? tiles
        : url.pathname.includes('land_price')
          ? roads
          : areas;
      return empty
        ? route.fulfill({ status: 204 })
        : route.fulfill({
            contentType: 'application/vnd.mapbox-vector-tile',
            body: Buffer.from(
              fromGeojsonVt({ features: source.getTile(z, x, y) ?? { features: [] } }),
            ),
          });
    }
    return route.fulfill({ status: 404 });
  });
  await page.goto('/tests/browser/data-layers.html');
  await page.waitForFunction('window.dataMap?.isStyleLoaded()');
  expect(await page.evaluate('Boolean(window.dataMap.getSource("urban-land-price"))')).toBe(false);
  await page.evaluate('window.dataMap.jumpTo({center:[106.7,10.8],zoom:14})');
  await page.getByRole('button', { name: 'Open data layers', exact: true }).click();
  const population = page.getByRole('checkbox', { name: 'Population', exact: true });
  await expect(population).toBeEnabled();
  await expect(page.getByRole('checkbox', { name: 'Land price', exact: true })).toBeDisabled();
  await population.check();
  await page.waitForFunction('Boolean(window.dataMap.getLayer("dataset-population"))');
  await page.evaluate('window.populationSource = window.dataMap.getSource("dataset-population")');
  await page.getByRole('slider', { name: 'Population opacity' }).fill('60');
  expect(
    await page.evaluate(
      'window.populationSource === window.dataMap.getSource("dataset-population")',
    ),
  ).toBe(true);
  await page.getByLabel('Population year', { exact: true }).selectOption('2022');
  await page.getByLabel('Population palette', { exact: true }).selectOption('fire');
  await expect
    .poll(() => page.evaluate('window.dataMap.getSource("dataset-population")?.tiles?.[0]'))
    .toContain('/2022/tiles/{z}/{x}/{y}.png?palette=fire');
  await page.getByRole('checkbox', { name: 'Flood history', exact: true }).check();
  await expect
    .poll(() =>
      page.evaluate(
        'window.dataMap.queryRenderedFeatures({layers:["dataset-flood-history"]}).length',
      ),
    )
    .toBeGreaterThan(0);
  await page.getByLabel('Flood start date').fill('2024-01-01');
  // Enabling a raster later must not obscure the vector observations.
  await population.uncheck();
  await population.check();
  await page.waitForFunction('Boolean(window.dataMap.getLayer("dataset-population"))');
  expect(
    await page.evaluate(
      `(() => { const ids=window.dataMap.getStyle().layers.map(l=>l.id); return ids.indexOf('dataset-population') < ids.indexOf('dataset-flood-history'); })()`,
    ),
  ).toBe(true);
  await page.getByLabel('Flood end date').fill('2025-01-01');
  await page.getByRole('button', { name: 'Apply', exact: true }).click();
  await expect
    .poll(() =>
      queries.some(
        (q) =>
          q.includes('/flood_history/features?') && q.includes('bbox=') && q.includes('start=2024'),
      ),
    )
    .toBe(true);
  await page.screenshot({ path: testInfo.outputPath('data-layer-controls.png') });
  await page.evaluate(
    'window.dataMap.setStyle({version:8,sources:{},layers:[{id:"replacement",type:"background",paint:{"background-color":"#304050"}}]})',
  );
  await page.waitForFunction(
    'window.dataMap.getLayer("dataset-population") && window.dataMap.getLayer("dataset-flood-history") && window.dataMap.getLayer("urban-distance-measurement")',
  );
  await page
    .getByRole('region', { name: 'Data layers' })
    .getByRole('button', { name: 'Close data layers' })
    .click();
  await page.mouse.click(500, 350);
  await expect(page.getByRole('complementary', { name: 'Dataset details' })).toContainText(
    'Cầu Ông Dầu, Phường Hiệp Bình Phước, Thủ Đức',
  );
  await expect(page.getByRole('complementary', { name: 'Dataset details' })).toContainText(
    'Approximate area · low precision',
  );
  await expect(page.getByRole('complementary', { name: 'Dataset details' })).toContainText(
    'Phường Hiệp Bình',
  );
  await page.getByRole('button', { name: 'Close dataset details' }).click();
  await page.getByRole('button', { name: 'Open data layers', exact: true }).click();
  empty = true;
  await page.getByRole('button', { name: 'Refresh data sources' }).click();
  await expect(page.getByText('No data in this area').first()).toBeVisible();
  fail = true;
  empty = false;
  await page.getByRole('button', { name: 'Refresh data sources' }).click();
  await expect(page.getByText('Data unavailable · retry')).toBeVisible();
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  fail = false;
  await expect(page.locator('.dataset-controls[data-state="ready"]')).toHaveCount(2);
  await expect(page.getByText('Data unavailable · retry')).toHaveCount(0);
  await page.getByRole('checkbox', { name: 'Flood history', exact: true }).uncheck();
  await population.uncheck();
  await expect
    .poll(() =>
      page.evaluate(
        'Boolean(window.dataMap.getSource("dataset-population") || window.dataMap.getSource("dataset-flood-history"))',
      ),
    )
    .toBe(false);
  prices = true;
  await page.getByRole('button', { name: 'Refresh data sources' }).click();
  await expect(page.getByRole('checkbox', { name: 'Land price', exact: true })).toBeEnabled();
  for (const [label, id] of [
    ['Flood risk', 'flood'],
    ['Flood satellite', 'flood-satellite'],
    ['Land price', 'land-price'],
  ]) {
    await page.getByRole('checkbox', { name: label, exact: true }).check();
    await expect
      .poll(() =>
        page.evaluate(
          (id) => window['dataMap'].queryRenderedFeatures({ layers: [`dataset-${id}`] }).length,
          id,
        ),
      )
      .toBeGreaterThan(0);
    await page.getByRole('checkbox', { name: label, exact: true }).uncheck();
  }
  await population.check();
  await page
    .getByRole('region', { name: 'Data layers' })
    .getByRole('button', { name: 'Close data layers' })
    .click();
  await page.getByRole('button', { name: 'Measurement tools' }).click();
  await page.getByRole('button', { name: 'Measure distance', exact: true }).click();
  await page.mouse.click(450, 350);
  await page.mouse.click(550, 350);
  await expect(page.getByRole('button', { name: 'Done', exact: true })).toBeEnabled();
  await expect(page.getByRole('complementary', { name: 'Dataset details' })).toHaveCount(0);
  expect(errors).toEqual([]);
});
