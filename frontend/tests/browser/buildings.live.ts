import { expect, test } from '@playwright/test';

test('Goong building geometry and elevation agree with the rendered scene', async ({ page }) => {
  await page.goto('/tests/browser/measurement.html?goong=1');
  await page.waitForFunction('window.harness?.map.areTilesLoaded() && window.harness.map.getLayer("urban-buildings-3d")');
  await page.waitForFunction('window.harness.map.queryRenderedFeatures({layers:["urban-buildings-3d"]}).length > 0 && window.harness.map.isSourceLoaded("urban-terrain-dem")');
  const data = await page.evaluate(`(() => {
    const map = window.harness.map;
    return { layers: map.getStyle().layers.filter(l => l.type === 'fill-extrusion'),
      features: map.queryRenderedFeatures({layers:['urban-buildings-3d']}).slice(0,8).map(f=>f.properties),
      terrain: map.queryTerrainElevation([106.703,10.776]) };
  })()`);
  expect(data.features.length).toBeGreaterThan(0);
  expect(data.layers.filter((l: { layout?: { visibility?: string } }) => l.layout?.visibility !== 'none')).toHaveLength(1);
  const target = await page.evaluate(`(() => {
    const h = window.harness;
    const feature = h.map.queryRenderedFeatures({layers:['urban-buildings-3d']})
      .find(f => f.properties.max_height >= 15 && f.properties.max_height <= 60 && f.geometry.type === 'Polygon');
    if (!feature) return null;
    const ring = feature.geometry.coordinates[0].slice(0,-1);
    const lng = ring.reduce((s,p)=>s+p[0],0)/ring.length;
    const lat = ring.reduce((s,p)=>s+p[1],0)/ring.length;
    const elevation = h.map.queryTerrainElevation([lng,lat]) + feature.properties.max_height;
    return { lng, lat, elevation, screen:h.project(lng,lat,elevation) };
  })()`);
  expect(target).not.toBeNull();
  await page.evaluate(`window.harness.map.jumpTo({center:[${target.lng},${target.lat}], zoom:17.5, pitch:55})`);
  await page.waitForFunction('window.harness.map.areTilesLoaded() && window.harness.map.isSourceLoaded("urban-terrain-dem")');
  const screen = await page.evaluate(`window.harness.project(${target.lng},${target.lat},${target.elevation})`);
  expect(screen.x).toBeGreaterThan(0);
  expect(screen.y).toBeGreaterThan(0);
  expect(screen.x).toBeLessThan(1000);
  expect(screen.y).toBeLessThan(700);
  await page.mouse.click(screen.x, screen.y);
  const point = await page.evaluate('window.harness.state().points[0]');
  expect(point.surface).toBe('building');
  expect(point.elevationAvailable).toBe(true);
  // A taller foreground building may occlude the requested roof: the nearest
  // visible surface must win, while still projecting exactly under the pointer.
  expect(point.buildingHeightMeters).toBeGreaterThan(0);
  const picked = await page.evaluate(`window.harness.project(${point.longitude},${point.latitude},${point.elevationMeters})`);
  expect(Math.hypot(picked.x - Math.floor(screen.x), picked.y - Math.floor(screen.y))).toBeLessThan(1.5);
  await page.evaluate('window.harness.reset()');
  await page.mouse.move(screen.x, screen.y + 15);
  await expect.poll(() => page.evaluate('window.harness.laserPixels().length')).toBeGreaterThan(5);
  await page.screenshot({ path: 'test-results/goong-building-height-guide.png' });
});
