import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 512;
    const context = canvas.getContext('2d')!;
    // Terrarium: R*256 + G + B/256 - 32768 = 80 metres.
    context.fillStyle = 'rgb(128,80,0)';
    context.fillRect(0, 0, 512, 512);
    return canvas.toDataURL().split(',')[1];
  });
  await page.route('https://tiles.mapterhorn.com/**', (route) => {
    if (route.request().url().endsWith('tilejson.json')) return route.fulfill({ json: {
      tilejson: '3.0.0', tiles: ['https://tiles.mapterhorn.com/{z}/{x}/{y}.webp'], encoding: 'terrarium', tileSize: 512,
    } });
    const zoom = Number(new URL(route.request().url()).pathname.split('/')[1]);
    return zoom <= 12 ? route.fulfill({ contentType: 'image/png', body: Buffer.from(png, 'base64') })
      : route.fulfill({ status: 404 });
  });
});

test('laser, roof selection and world anchors survive camera and mode changes', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto('/tests/browser/measurement.html');
  await expect.poll(async () => ({
    state: await page.evaluate('window.harness ? { loaded: window.harness.map.isStyleLoaded(), elevation: window.harness.map.queryTerrainElevation([106.7,10.8]) } : null'),
    errors,
  }), { timeout: 15000 }).toEqual({ state: { loaded: true, elevation: 80 }, errors: [] });

  const guideWall = await page.evaluate('window.harness.project(106.7,10.7998,120)') as { x: number; y: number };
  await page.mouse.move(guideWall.x, guideWall.y);
  await expect.poll(() => page.evaluate('window.harness.laserPixels().length')).toBeGreaterThan(30);
  const laserPixels = await page.evaluate('window.harness.laserPixels()') as number[][];
  // A height slice hugs the wall; an X through empty space fails this check.
  expect(laserPixels.filter(([,y]) => Math.abs(y - guideWall.y) > 3).length).toBeLessThan(10);
  for (let frame = 0; frame < 2; frame++) {
    await page.evaluate(`new Promise(resolve => {
      window.harness.map.once('render', resolve);
      window.harness.map.triggerRepaint();
    })`);
    expect(await page.evaluate('window.harness.laserPixels()')).toEqual(laserPixels);
  }

  // A non-central roof point must stay under the pointer, not snap to the centroid.
  const roof = await page.evaluate('window.harness.project(106.7001, 10.80005, 160)') as { x: number; y: number };
  await page.mouse.click(roof.x, roof.y);
  const points = await page.evaluate('window.harness.state().points') as { longitude: number; latitude: number; elevationMeters: number; surface: string }[];
  expect(points).toHaveLength(1);
  expect(points[0].surface).toBe('building');
  const pickedScreen = await page.evaluate(`window.harness.project(${points[0].longitude}, ${points[0].latitude}, ${points[0].elevationMeters})`) as { x: number; y: number };
  // Browser mouse events use CSS pixel coordinates; require sub-pixel agreement.
  expect(Math.hypot(pickedScreen.x - Math.floor(roof.x), pickedScreen.y - Math.floor(roof.y))).toBeLessThan(1.5);
  expect(points[0].elevationMeters).toBeCloseTo(160, 1);

  await page.mouse.click(220, 490);
  await page.evaluate('window.harness.done()');
  const fixed = await page.evaluate('window.harness.state().points');
  for (const camera of [{ zoom: 17.5, bearing: 90, pitch: 65 }, { zoom: 16, bearing: 180, pitch: 35 }, { zoom: 17, bearing: -90, pitch: 60 }]) {
    await page.evaluate((camera) => {
      const h = (window as unknown as { harness: { map: { jumpTo: (camera: object) => void } } }).harness;
      h.map.jumpTo(camera);
    }, camera);
    await expect.poll(() => page.evaluate('window.harness.pixels().yellow')).toBeGreaterThan(30);
    expect(await page.evaluate('window.harness.state().points')).toEqual(fixed);
    expect(await page.evaluate('window.harness.pixels().error')).toBe(0);
    await expect.poll(() => page.evaluate(`window.harness.markerError(${points[0].longitude}, ${points[0].latitude}, ${points[0].elevationMeters})`)).toBeLessThan(5);
  }
  await page.evaluate('window.harness.mode("2d")');
  await page.waitForFunction('window.harness.map.getPitch() === 0');
  expect(await page.evaluate('window.harness.state().points')).toEqual(fixed);
  await page.evaluate('window.harness.mode("3d")');
  await expect.poll(() => page.evaluate('window.harness.pixels().yellow')).toBeGreaterThan(30);
  expect(await page.evaluate('window.harness.state().points')).toEqual(fixed);
  expect(errors).toEqual([]);
  await page.screenshot({ path: 'test-results/measurement-3d.png' });
});

test('clicks a building facade at the pointer height rather than jumping to the roof', async ({ page }) => {
  await page.goto('/tests/browser/measurement.html');
  await page.waitForFunction('window.harness?.map.isStyleLoaded() && window.harness.map.queryTerrainElevation([106.7,10.8]) === 80');
  const wall = await page.evaluate('window.harness.project(106.7,10.7998,120)') as { x: number; y: number };
  await page.mouse.click(wall.x, wall.y);
  const state = await page.evaluate('window.harness.state().points[0]') as { surface: string; elevationMeters: number };
  expect(state.surface).toBe('building');
  expect(state.elevationMeters).toBeGreaterThan(115);
  expect(state.elevationMeters).toBeLessThan(125);
});

test('height guide follows sloping terrain without rebuilding the scene', async ({ page }) => {
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 512;
    const ctx = canvas.getContext('2d')!;
    for (let x = 0; x < 512; x++) {
      ctx.fillStyle = `rgb(128,${80 + Math.floor(x / 4)},${(x % 4) * 64})`;
      ctx.fillRect(x, 0, 1, 512);
    }
    return canvas.toDataURL().split(',')[1];
  });
  await page.route('https://tiles.mapterhorn.com/**/*.webp', route => route.fulfill({
    contentType: 'image/png', body: Buffer.from(png, 'base64'),
  }));
  await page.goto('/tests/browser/measurement.html?live=1');
  await page.waitForFunction('window.harness?.map.areTilesLoaded() && window.harness.map.isSourceLoaded("urban-terrain-dem")');
  await page.mouse.move(500, 400);
  await expect.poll(() => page.evaluate('window.harness.laserPixels().length')).toBeGreaterThan(30);
  expect(await page.evaluate('window.harness.state().preview.surface')).toBe('terrain');
  const contour = await page.evaluate('window.harness.laserPixels()') as number[][];
  // The 12px cursor sphere covers the intersection itself.
  expect(Math.min(...contour.map(([x,y]) => Math.hypot(x-500,y-400)))).toBeLessThan(9);
  expect(await page.evaluate('window.harness.pixels().error')).toBe(0);
  await page.screenshot({ path: 'test-results/terrain-height-guide.png' });
  await page.setViewportSize({ width: 850, height: 600 });
  await page.mouse.move(450, 350);
  await expect.poll(() => page.evaluate('window.harness.laserPixels().length')).toBeGreaterThan(30);
  expect(await page.evaluate('window.harness.pixels().error')).toBe(0);
  await page.evaluate('window.harness.done()');
  await expect.poll(() => page.evaluate('window.harness.laserPixels().length')).toBe(0);
});
