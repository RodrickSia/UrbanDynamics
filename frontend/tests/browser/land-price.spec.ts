import { expect, test } from '@playwright/test';
import { GeoJSONVT } from '@maplibre/geojson-vt';
import { fromGeojsonVt } from '@maplibre/vt-pbf';

test('renders priced vector segments, opens details, and restores the layer after a style change', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const prices = new GeoJSONVT({type:'Feature', properties:{road:'Fixture road', ward:'Fixture ward',
    residential_vnd_m2:100000000, commercial_vnd_m2:60000000, other_nonagricultural_vnd_m2:50000000,
    match_confidence:'spatially_checked', geometry_coverage:'between_named_intersections_within_ward'},
    geometry:{type:'LineString', coordinates:[[106.699,10.8],[106.701,10.8]]}}, {maxZoom:18});
  await page.route('https://tiles.goong.io/**', route => route.fulfill({json:{version:8, sources:{},
    layers:[{id:'background',type:'background',paint:{'background-color':'#233440'}}]}}));
  await page.route('https://satellite.goong.io/**', route => route.fulfill({contentType:'image/png',
    body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK1cAAAAASUVORK5CYII=','base64')}));
  await page.route('**/api/v1/layers/land_price/tilejson.json', route => route.fulfill({json:{
    metadata:{matched_rows:1,source_rows:2,pending_rows:1,updated_at:'fixture-version'}}}));
  await page.route('**/api/v1/layers/land_price/tiles/**', route => {
    const [z,x,y] = new URL(route.request().url()).pathname.split('/tiles/')[1].match(/\d+/g)!.map(Number);
    return route.fulfill({contentType:'application/vnd.mapbox-vector-tile',
      body:Buffer.from(fromGeojsonVt({features:prices.getTile(z,x,y) ?? {features:[]}}))});
  });
  await page.goto('/tests/browser/workspace.html');
  await page.waitForFunction('window.workspace?.map()?.isStyleLoaded()');
  await page.evaluate('window.workspace.map().jumpTo({center:[106.7,10.8],zoom:16}); window.workspace.measurement({status:"idle",points:[],preview:null}); window.workspace.landPrice(true)');
  await expect(page.getByLabel('Land price legend')).toContainText('1 mapped / 2 source rows');
  await page.waitForFunction('window.workspace.map().getLayer("urban-land-price-lines") && window.workspace.map().queryRenderedFeatures({layers:["urban-land-price-lines"]}).length > 0');
  const point = await page.evaluate('window.workspace.map().project([106.7,10.8])') as {x:number;y:number};
  await page.mouse.click(point.x, point.y);
  await expect(page.getByRole('region', {name:'Land price details',exact:true})).toContainText('100.000.000 ₫/m²');
  await expect(page.getByRole('region', {name:'Land price details',exact:true})).toContainText('Spatial match · not manually reviewed');
  await page.evaluate('window.workspace.opacity(.4)');
  await expect.poll(() => page.evaluate('window.workspace.map().getPaintProperty("urban-land-price-lines","line-opacity")')).toBe(.4);
  await page.evaluate('window.workspace.style("satellite")');
  await page.waitForFunction('window.workspace.map().getLayer("satellite-imagery") && window.workspace.map().isStyleLoaded() && window.workspace.map().getLayer("urban-land-price-lines") && window.workspace.map().queryRenderedFeatures({layers:["urban-land-price-lines"]}).length > 0');
  await page.screenshot({path:'test-results/land-price-map.png'});
  await page.evaluate('window.workspace.landPrice(false)');
  await expect(page.getByLabel('Land price legend')).toHaveCount(0);
  expect(await page.evaluate('Boolean(window.workspace.map().getSource("urban-land-price"))')).toBe(false);
  expect(errors).toEqual([]);
});
