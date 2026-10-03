import { expect, test } from '@playwright/test';

test('Ben Tre zero-height footprints render above terrain without claiming real building elevations', async ({ page }) => {
  await page.goto('/tests/browser/measurement.html?goong=1');
  await page.waitForFunction('window.harness?.map.areTilesLoaded() && window.harness.map.isSourceLoaded("urban-terrain-dem")');
  await page.evaluate('window.harness.map.jumpTo({center:[106.375,10.243],zoom:17.5,pitch:60})');
  await page.waitForFunction('window.harness.map.areTilesLoaded()');
  const target = await page.evaluate(`(() => {
    const map = window.harness.map;
    const features = map.queryRenderedFeatures({layers:['urban-buildings-3d']});
    for (const feature of features) {
      if (feature.properties.max_height !== 0 || feature.geometry.type !== 'Polygon') continue;
      const ring = feature.geometry.coordinates[0].slice(0,-1);
      if (ring.length !== 4) continue;
      const lng = ring.reduce((s,p) => s+p[0],0)/ring.length;
      const lat = ring.reduce((s,p) => s+p[1],0)/ring.length;
      const p = window.harness.project(lng,lat,map.queryTerrainElevation([lng,lat])+12);
      if (p.x > 200 && p.x < 800 && p.y > 150 && p.y < 550) return {lng,lat};
    }
    return null;
  })()`);
  expect(target).not.toBeNull();
  await page.evaluate(`window.harness.map.jumpTo({center:[${target.lng},${target.lat}],zoom:19,pitch:60})`);
  await page.waitForFunction('window.harness.map.areTilesLoaded()');
  await page.evaluate('window.harness.map.setPaintProperty("urban-buildings-3d","fill-extrusion-opacity",0.8)');
  await page.evaluate(`new Promise(resolve => { window.harness.map.once('render', resolve); window.harness.map.triggerRepaint(); })`);
  const pixel = await page.evaluate(`window.harness.project(${target.lng},${target.lat},window.harness.map.queryTerrainElevation([${target.lng},${target.lat}])+12)`);
  await page.mouse.click(pixel.x,pixel.y);
  expect(await page.evaluate('window.harness.state().points[0]')).toMatchObject({ surface:'building', elevationAvailable:false });
  expect(await page.evaluate('window.harness.map.getTerrain().exaggeration')).toBe(1);
  expect(await page.evaluate('window.harness.pixels().error')).toBe(0);
  await page.screenshot({ path: 'playwright-report/ben-tre-buildings-fixed.png' });
});
