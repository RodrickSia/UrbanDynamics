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
  await expect.poll(() => page.evaluate('window.harness.state().preview?.snap?.kind')).toBe('face');
  await expect(page.locator('.measurement-distance-pill')).toHaveCount(0);
  // The height reference is available immediately; it is not a distance
  // component and must not depend on a first anchor or the Components switch.
  expect(await page.evaluate('window.harness.state().points.length')).toBe(0);
  expect(await page.evaluate('!!window.harness.state().showComponents')).toBe(false);
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

  await page.screenshot({ path: 'test-results/laser-before-first-click.png' });
  // Check disappearance before adding an orange/white distance line: its
  // antialiased pixels can also match the amber pixel detector.
  await page.evaluate('window.harness.done()');
  await expect.poll(() => page.evaluate('window.harness.laserPixels().length')).toBe(0);
  await page.evaluate('window.harness.reset()');
  await page.mouse.click(220, 490);
  await page.mouse.move(guideWall.x, guideWall.y);
  await expect(page.locator('.measurement-distance-pill')).toHaveCount(1);
  await expect.poll(() => page.evaluate('window.harness.laserPixels().length')).toBeGreaterThan(30);
  await page.evaluate('window.harness.components(true)');
  await expect(page.locator('.measurement-distance-pill')).toHaveCount(3);
  await page.evaluate('window.harness.components(false)');
  await expect(page.locator('.measurement-distance-pill')).toHaveCount(1);
  await expect.poll(() => page.evaluate('window.harness.laserPixels().length')).toBeGreaterThan(30);

  await page.evaluate('window.harness.reset()');

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
  const label = page.locator('.measurement-distance-pill');
  await expect(label).toHaveCount(1);
  await expect(label).toBeVisible();
  // Compare settled CSS-pixel sizes, not a frame in the entrance scale tween.
  await expect(label).toHaveCSS('transform', 'none');
  const initialLabelStyle = await label.evaluate((element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return {
      width: rect.width,
      height: rect.height,
      fontSize: style.fontSize,
      color: style.color,
      borderRadius: style.borderRadius,
      backgroundColor: style.backgroundColor,
    };
  });
  expect(initialLabelStyle.fontSize).toBe('11px');
  expect(initialLabelStyle.color).toBe('rgb(255, 255, 255)');
  expect(initialLabelStyle.borderRadius).toBe('999px');
  expect(initialLabelStyle.backgroundColor).toContain('0.84');
  await page.evaluate('window.harness.done()');
  const fixed = await page.evaluate('window.harness.state().points');
  for (const camera of [{ zoom: 17.5, bearing: 90, pitch: 65 }, { zoom: 16, bearing: 180, pitch: 35 }, { zoom: 17, bearing: -90, pitch: 60 }]) {
    await page.evaluate((camera) => {
      const h = (window as unknown as { harness: { map: { jumpTo: (camera: object) => void } } }).harness;
      h.map.jumpTo(camera);
    }, camera);
    await expect.poll(() => page.evaluate('window.harness.pixels().direct')).toBeGreaterThan(30);
    expect(await page.evaluate('window.harness.state().points')).toEqual(fixed);
    expect(await page.evaluate('window.harness.pixels().error')).toBe(0);
    await expect.poll(() => page.evaluate(`window.harness.markerError(${points[0].longitude}, ${points[0].latitude}, ${points[0].elevationMeters})`)).toBeLessThan(5);
    const size = await label.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    });
    expect(Math.abs(size.width - initialLabelStyle.width)).toBeLessThan(1);
    expect(Math.abs(size.height - initialLabelStyle.height)).toBeLessThan(1);
  }
  await page.evaluate('window.harness.mode("2d")');
  await page.waitForFunction('window.harness.map.getPitch() === 0');
  expect(await page.evaluate('window.harness.state().points')).toEqual(fixed);
  await page.evaluate('window.harness.mode("3d")');
  await expect.poll(() => page.evaluate('window.harness.pixels().direct')).toBeGreaterThan(30);
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

test('hides the hover sphere at a committed point and resumes for the next segment', async ({ page }) => {
  await page.goto('/tests/browser/measurement.html');
  await page.waitForFunction('window.harness?.map.isStyleLoaded() && window.harness.map.queryTerrainElevation([106.7,10.8]) === 80');
  await page.mouse.click(220,490);
  await page.mouse.click(350,490);
  expect(await page.evaluate('window.harness.state().points.length')).toBe(2);
  await page.mouse.move(351,490);
  // Wait for the queued preview/render, including tiny mouse jitter after click.
  await page.evaluate(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
  expect(await page.evaluate('window.harness.state().preview')).toBeNull();
  await expect(page.locator('.measurement-distance-pill')).toHaveCount(1);
  await page.mouse.move(400,450);
  await expect.poll(() => page.evaluate('window.harness.state().preview')).not.toBeNull();
  await page.mouse.click(400,450);
  expect(await page.evaluate('window.harness.state().points.length')).toBe(3);
  await page.evaluate('window.harness.done()');
  expect(await page.evaluate('window.harness.state().preview')).toBeNull();
});

test('zero-height building data uses only the visual fallback above terrain, never a fake measurement height', async ({ page }) => {
  await page.goto('/tests/browser/measurement.html?height=0');
  await page.waitForFunction('window.harness?.map.isStyleLoaded() && window.harness.map.queryTerrainElevation([106.7,10.8]) === 80');
  // The existing visual-only fallback is 12 m. A zero-height extrusion would
  // put this screen point on the background/ground, not a building facade.
  const roof = await page.evaluate('window.harness.project(106.7,10.80019,92)') as { x: number; y: number };
  const pixel = await page.evaluate(({ x,y }) => {
    const gl = document.querySelector('canvas')!.getContext('webgl2')!;
    const data = new Uint8Array(4);
    gl.readPixels(Math.floor(x),gl.drawingBufferHeight - Math.floor(y) - 1,1,1,gl.RGBA,gl.UNSIGNED_BYTE,data);
    return Array.from(data);
  }, roof);
  expect(pixel[0]).toBeGreaterThan(80);
  expect(pixel[1]).toBeGreaterThan(80);
  const facade = await page.evaluate('window.harness.project(106.7,10.7998,86)') as { x: number; y: number };
  await page.mouse.click(facade.x,facade.y);
  expect(await page.evaluate('window.harness.state().points[0]')).toMatchObject({
    surface:'building', elevationAvailable:false, elevationMeters:80,
  });
});

test('snaps the complete real edge before measuring and stores both endpoint contexts', async ({ page }) => {
  await page.goto('/tests/browser/measurement.html');
  await page.waitForFunction('window.harness?.map.isStyleLoaded() && window.harness.map.queryTerrainElevation([106.7,10.8]) === 80');
  const hover = await page.evaluate('window.harness.project(106.7,10.7998,160)') as { x: number; y: number };
  await page.mouse.move(hover.x, hover.y);
  await expect.poll(() => page.evaluate('window.harness.state().preview?.snap?.kind')).toBe('edge');
  await expect(page.locator('.measurement-distance-pill')).toHaveCount(0);
  expect(await page.evaluate('window.harness.state().preview.snap.edges.length')).toBe(1);
  // The whole edge is highlighted, even though no start point exists yet.
  await page.screenshot({ path: 'test-results/measurement-edge-hover.png' });
  for (const lng of [106.6998, 106.7002]) {
    const vertex = await page.evaluate(lng => {
      return (window as unknown as { harness: { project: (x: number, y: number, z: number) => { x: number; y: number } } }).harness.project(lng,10.7998,160);
    }, lng);
    await page.mouse.move(vertex.x, vertex.y);
    await expect.poll(() => page.evaluate('window.harness.state().preview?.snap?.kind')).toBe('vertex');
    await page.mouse.click(vertex.x, vertex.y);
  }
  await page.evaluate('window.harness.components(true)');
  await page.evaluate('window.harness.done()');
  await expect(page.locator('.measurement-distance-pill')).toHaveCount(1);
  await expect(page.locator('.measurement-distance-pill')).toHaveText(/43\.\d{2} m/);
  expect(await page.evaluate(`(() => {
    const [a,b] = window.harness.state().points;
    return a.snap.edges.some(edge => b.snap.edges.some(other => other.id === edge.id));
  })()`)).toBe(true);
  const fixed = await page.evaluate('window.harness.state().points');
  await page.evaluate('window.harness.map.jumpTo({ bearing: 50, pitch: 70, zoom: 18 })');
  await expect(page.locator('.measurement-distance-pill')).toBeVisible();
  expect(await page.evaluate('window.harness.state().points')).toEqual(fixed);
  expect(await page.evaluate('window.harness.pixels().error')).toBe(0);
  await page.screenshot({ path: 'test-results/measurement-edge-selected.png' });
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
  await expect(page.locator('.measurement-distance-pill')).toHaveCount(0);
  expect(await page.evaluate('window.harness.state().preview.surface')).toBe('terrain');
  const contour = await page.evaluate('window.harness.laserPixels()') as number[][];
  // The 12px cursor sphere covers the intersection itself.
  expect(Math.min(...contour.map(([x,y]) => Math.hypot(x-500,y-400)))).toBeLessThan(9);
  expect(await page.evaluate('window.harness.pixels().error')).toBe(0);
  await page.screenshot({ path: 'test-results/terrain-height-guide.png' });
  await page.setViewportSize({ width: 850, height: 600 });
  await page.evaluate(`new Promise(resolve => {
    window.harness.map.once('render', resolve);
    window.harness.map.resize();
    window.harness.map.triggerRepaint();
  })`);
  await page.mouse.move(450, 350);
  await expect.poll(() => page.evaluate('window.harness.laserPixels().length')).toBeGreaterThan(30);
  expect(await page.evaluate('window.harness.pixels().error')).toBe(0);
  await page.evaluate('window.harness.done()');
  await page.evaluate('window.harness.components(false)');
  await expect.poll(() => page.evaluate('window.harness.laserPixels().length')).toBe(0);
});

test('partial vertical edge measurements stay on the facade and hidden vertices cannot win', async ({ page }) => {
  await page.goto('/tests/browser/measurement.html');
  await page.waitForFunction('window.harness?.map.isStyleLoaded() && window.harness.map.queryTerrainElevation([106.7,10.8]) === 80');
  const hidden = await page.evaluate('window.harness.project(106.6998,10.8002,80)') as { x: number; y: number };
  await page.mouse.move(hidden.x, hidden.y);
  await expect.poll(() => page.evaluate('window.harness.state().preview?.elevationMeters')).toBeGreaterThan(90);
  expect(await page.evaluate('window.harness.state().preview.snap.kind')).not.toBe('ground');
  for (const elevation of [110, 140]) {
    const pixel = await page.evaluate(elevation => {
      return (window as unknown as { harness: { project: (x: number, y: number, z: number) => { x: number; y: number } } }).harness.project(106.7002,10.7998,elevation);
    }, elevation);
    await page.mouse.move(pixel.x - 2, pixel.y);
    await expect.poll(() => page.evaluate('window.harness.state().preview?.snap?.kind')).toBe('edge');
    await page.mouse.click(pixel.x - 2, pixel.y);
  }
  await page.evaluate('window.harness.components(true)');
  await page.evaluate('window.harness.done()');
  await expect(page.locator('.measurement-distance-pill')).toHaveCount(1);
  const points = await page.evaluate('window.harness.state().points') as { longitude: number; latitude: number; elevationMeters: number }[];
  expect(points[0].longitude).toBeCloseTo(points[1].longitude, 9);
  expect(points[0].latitude).toBeCloseTo(points[1].latitude, 9);
  expect(points[1].elevationMeters - points[0].elevationMeters).toBeGreaterThan(29);
  expect(points[1].elevationMeters - points[0].elevationMeters).toBeLessThan(31);
  await page.screenshot({ path: 'test-results/measurement-vertical-edge.png' });
});
