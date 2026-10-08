import { expect, test, type Page } from '@playwright/test';

async function settledFrame(page: Page) {
  await page.evaluate(`new Promise(resolve=>{
    const map=window.viewshedHarness.map;
    map.once('idle',()=>resolve(undefined));map.triggerRepaint();
  })`);
}

/** Assert the presented image, independently of MapLibre's offscreen FBO state. */
async function scenePixel(page: Page, latitude: number, elevation?: number) {
  // Offset from the center ray so the SVG observer/target arrows cannot cover
  // the surface pixel. This still lies inside the building's physical shadow.
  const p = (await page.evaluate(
    `window.viewshedHarness.project(106.70008,${latitude},${elevation ?? `window.viewshedHarness.map.queryTerrainElevation([106.70008,${latitude}])`})`,
  )) as { x: number; y: number };
  const png = await page.screenshot({
    clip: { x: Math.round(p.x), y: Math.round(p.y), width: 1, height: 1 },
  });
  return page.evaluate(async (base64) => {
    const image = new Image();
    image.src = `data:image/png;base64,${base64}`;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const context = canvas.getContext('2d')!;
    context.drawImage(image, 0, 0);
    return Array.from(context.getImageData(0, 0, 1, 1).data);
  }, png.toString('base64'));
}

test.beforeEach(async ({ page }) => {
  const png = await page.evaluate(() => {
    const c = document.createElement('canvas');
    c.width = c.height = 512;
    const ctx = c.getContext('2d')!;
    ctx.fillStyle = 'rgb(128,80,0)';
    ctx.fillRect(0, 0, 512, 512);
    return c.toDataURL().split(',')[1];
  });
  await page.route('https://tiles.mapterhorn.com/**', (route) =>
    route.request().url().endsWith('tilejson.json')
      ? route.fulfill({
          json: {
            tilejson: '3.0.0',
            tiles: ['https://tiles.mapterhorn.com/{z}/{x}/{y}.webp'],
            encoding: 'terrarium',
            tileSize: 512,
          },
        })
      : route.fulfill({
          contentType: 'image/png',
          body: Buffer.from(png, 'base64'),
        }),
  );
});

test('classifies real obstruction, survives camera/style changes, and edits world handles', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  await page.goto('/tests/browser/viewshed.html');
  await expect
    .poll(() => page.evaluate('window.viewshedHarness?.map.queryTerrainElevation([106.7,10.8])'))
    .toBe(80);
  await page.evaluate(`window.viewshedHarness.onAction({type:'start'})`);
  await expect.poll(() => page.evaluate('window.viewshedHarness.state.phase')).toBe('observer');
  await settledFrame(page);
  const observer = (await page.evaluate('window.viewshedHarness.project(106.7,10.7994,80)')) as {
    x: number;
    y: number;
  };
  await page.mouse.click(observer.x, observer.y);
  await expect.poll(() => page.evaluate('window.viewshedHarness.state.phase')).toBe('target');
  const target = (await page.evaluate('window.viewshedHarness.project(106.7,10.8008,80)')) as {
    x: number;
    y: number;
  };
  await page.mouse.move(target.x, target.y);
  await expect
    .poll(() => page.evaluate('window.viewshedHarness.state.items[0].target.latitude'))
    .toBeGreaterThan(10.8005);
  await page.mouse.click(target.x, target.y);
  await expect.poll(() => page.evaluate('window.viewshedHarness.state.phase')).toBe('editing');
  await expect.poll(() => page.evaluate('window.viewshedHarness.status')).toContain('Loaded scene');
  const before = await page.evaluate('JSON.stringify(window.viewshedHarness.state.items)');
  // Green ground in front of the building, red ground behind it.
  await expect
    .poll(async () => {
      const [r, g] = await scenePixel(page, 10.7997, 80);
      return g - r;
    })
    .toBeGreaterThan(20);
  await expect
    .poll(async () => {
      // Far enough behind the roof to remain visible to the main map camera.
      const [r, g] = await scenePixel(page, 10.80065, 80);
      return r - g;
    })
    .toBeGreaterThan(20);
  await page.screenshot({ path: 'test-results/viewshed-analysis.png' });
  await page.evaluate('window.viewshedHarness.map.jumpTo({bearing:35,pitch:62,zoom:17.3})');
  expect(await page.evaluate('JSON.stringify(window.viewshedHarness.state.items)')).toBe(before);
  await page.getByRole('button', { name: 'Close viewshed editing' }).click();
  await expect(page.getByRole('region', { name: 'Viewshed analysis' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Edit viewshed 1' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Distance (m)', { exact: true })).toBeVisible();
  await page.getByLabel('Distance (m)', { exact: true }).fill('180');
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Distance (m)', { exact: true })).toHaveValue('180');
  const originBefore = (await page.evaluate(
    'window.viewshedHarness.state.items[0].observer.elevationMeters',
  )) as number;
  const vertical = page.locator('.viewshed-arrow-group').first().locator('.viewshed-hit');
  const box = await vertical.boundingBox();
  expect(box).toBeTruthy();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2 - 25, { steps: 5 });
  await page.mouse.up();
  await expect
    .poll(() => page.evaluate('window.viewshedHarness.state.items[0].observer.elevationMeters'))
    .toBeGreaterThan(originBefore);
  expect(await page.evaluate('window.viewshedHarness.map.dragPan.isEnabled()')).toBe(true);
  const fixedObserver = await page.evaluate('window.viewshedHarness.state.items[0].observer');
  const oldTarget = await page.evaluate('window.viewshedHarness.state.items[0].target');
  const targetAxis = await page
    .locator('.viewshed-arrow-group')
    .nth(1)
    .locator('.viewshed-hit')
    .boundingBox();
  expect(targetAxis).toBeTruthy();
  await page.mouse.move(
    targetAxis!.x + targetAxis!.width / 2,
    targetAxis!.y + targetAxis!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    targetAxis!.x + targetAxis!.width / 2 + 22,
    targetAxis!.y + targetAxis!.height / 2,
    { steps: 5 },
  );
  await page.mouse.up();
  await expect
    .poll(() => page.evaluate('window.viewshedHarness.state.items[0].target'))
    .not.toEqual(oldTarget);
  expect(await page.evaluate('window.viewshedHarness.state.items[0].observer')).toEqual(
    fixedObserver,
  );
  const discPoint = await page.locator('.viewshed-disc-group .viewshed-hit').getAttribute('points');
  const [discX, discY] = discPoint!.split(' ')[8].split(',').map(Number);
  await page.mouse.move(discX, discY);
  await page.mouse.down();
  await page.mouse.move(discX + 20, discY, { steps: 5 });
  await page.mouse.up();
  await expect
    .poll(() => page.evaluate('window.viewshedHarness.state.items[0].observer'))
    .not.toEqual(fixedObserver);
  expect(await page.evaluate('window.viewshedHarness.map.dragPan.isEnabled()')).toBe(true);
  const edited = await page.evaluate('JSON.stringify(window.viewshedHarness.state.items)');
  await page.evaluate('window.viewshedHarness.reload()');
  await expect.poll(() => page.evaluate('window.viewshedHarness.map.isStyleLoaded()')).toBe(true);
  await expect.poll(() => page.evaluate('window.viewshedHarness.status')).toContain('Loaded scene');
  expect(await page.evaluate('JSON.stringify(window.viewshedHarness.state.items)')).toBe(edited);
  await page.evaluate(`window.viewshedHarness.mode('2d')`);
  await expect(page.getByLabel('Viewshed spatial handles')).toHaveCount(0);
  await page.evaluate(`window.viewshedHarness.mode('3d')`);
  await expect(page.getByLabel('Viewshed spatial handles')).toBeVisible();
  expect(await page.evaluate('JSON.stringify(window.viewshedHarness.state.items)')).toBe(edited);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('button', { name: 'Close viewshed editing' })).toBeInViewport();
  await page.screenshot({ path: 'test-results/viewshed-mobile.png' });
  expect(await page.evaluate('window.viewshedHarness.glError()')).toBe(0);
  expect(errors).toEqual([]);
  await page.evaluate('window.viewshedHarness.onAction({type:"delete"})');
  await expect.poll(() => page.evaluate('window.viewshedHarness.state.items.length')).toBe(0);
});

test('terrain ridge obstructs the far side without building geometry', async ({ page }) => {
  await page.route('https://tiles.mapterhorn.com/**/*.webp', async (route) => {
    const [z, , y] = new URL(route.request().url()).pathname
      .slice(1)
      .replace('.webp', '')
      .split('/')
      .map(Number);
    const png = await page.evaluate(
      ({ z, y }) => {
        const c = document.createElement('canvas');
        c.width = c.height = 512;
        const ctx = c.getContext('2d')!;
        for (let row = 0; row < 512; row++) {
          const lat =
            (Math.atan(Math.sinh(Math.PI * (1 - (2 * (y + (row + 0.5) / 512)) / 2 ** z))) * 180) /
            Math.PI;
          const height = 80 + 80 * Math.exp(-(((lat - 10.8) / 0.00035) ** 2));
          const encoded = Math.round((height + 32768) * 256);
          ctx.fillStyle = `rgb(${Math.floor(encoded / 65536)},${Math.floor(encoded / 256) % 256},${encoded % 256})`;
          ctx.fillRect(0, row, 512, 1);
        }
        return c.toDataURL().split(',')[1];
      },
      { z, y },
    );
    await route.fulfill({
      contentType: 'image/png',
      body: Buffer.from(png, 'base64'),
    });
  });
  await page.goto('/tests/browser/viewshed.html');
  await expect.poll(() => page.evaluate('window.viewshedHarness?.map.areTilesLoaded()')).toBe(true);
  await page.evaluate(`window.viewshedHarness.map.setLayoutProperty('urban-buildings-3d','visibility','none');
    window.viewshedHarness.map.jumpTo({pitch:0,zoom:17});
    window.viewshedHarness.onAction({type:'start'});`);
  await expect.poll(() => page.evaluate('window.viewshedHarness.state.phase')).toBe('observer');
  await page.evaluate(
    `window.viewshedHarness.onAction({type:'place',id:'hill',point:{longitude:106.7,latitude:10.799,elevationMeters:90}})`,
  );
  await expect.poll(() => page.evaluate('window.viewshedHarness.state.phase')).toBe('target');
  await page.evaluate(
    `window.viewshedHarness.onAction({type:'place',id:'end',point:{longitude:106.7,latitude:10.801,elevationMeters:90}})`,
  );
  await expect.poll(() => page.evaluate('window.viewshedHarness.status')).toContain('Terrain only');
  await settledFrame(page);
  await expect
    .poll(async () => {
      const [r, g] = await scenePixel(page, 10.8008);
      return r - g;
    })
    .toBeGreaterThan(20);
  for (const latitude of [10.7993, 10.7994, 10.7995, 10.7996, 10.7997]) {
    await expect
      .poll(async () => {
        const [r, g] = await scenePixel(page, latitude);
        return g - r;
      })
      .toBeGreaterThan(20);
  }
  await page.screenshot({ path: 'test-results/viewshed-terrain.png' });
  expect(await page.evaluate('window.viewshedHarness.glError()')).toBe(0);
});

test('direction handles keep range fixed and all four edges resize FOV only', async ({ page }) => {
  await page.goto('/tests/browser/viewshed.html');
  await expect.poll(() => page.evaluate('window.viewshedHarness?.map.areTilesLoaded()')).toBe(true);
  await page.evaluate('window.viewshedHarness.map.jumpTo({bearing:40,zoom:18})');
  await page.evaluate(`window.viewshedHarness.onAction({type:'start'})`);
  await expect.poll(() => page.evaluate('window.viewshedHarness.state.phase')).toBe('observer');
  await page.evaluate(
    `window.viewshedHarness.onAction({type:'place',id:'controls',point:{longitude:106.7,latitude:10.7999,elevationMeters:90}})`,
  );
  await expect.poll(() => page.evaluate('window.viewshedHarness.state.phase')).toBe('target');
  await page.evaluate(
    `window.viewshedHarness.onAction({type:'place',id:'end',point:{longitude:106.7,latitude:10.8004,elevationMeters:94}})`,
  );
  await expect.poll(() => page.evaluate('window.viewshedHarness.state.phase')).toBe('editing');
  await settledFrame(page);
  const values = () =>
    page.evaluate(
      `(async()=>{const {direction}=await import('/src/features/map/viewshed/math.ts');return direction(window.viewshedHarness.state.items[0]);})()`,
    ) as Promise<{ heading: number; tilt: number; distance: number }>;
  for (const handle of ['heading', 'tilt', 'distance']) {
    const before = await values();
    const line = page.locator(`[data-handle="${handle}"] .viewshed-hit`);
    const p = await line.evaluate((el) => {
      const x1 = Number(el.getAttribute('x1')),
        y1 = Number(el.getAttribute('y1')),
        x2 = Number(el.getAttribute('x2')),
        y2 = Number(el.getAttribute('y2'));
      const length = Math.hypot(x2 - x1, y2 - y1);
      return {
        x: x1 + (x2 - x1) * 0.75,
        y: y1 + (y2 - y1) * 0.75,
        dx: ((x2 - x1) / length) * 22,
        dy: ((y2 - y1) / length) * 22,
      };
    });
    await page.mouse.move(p.x, p.y);
    await page.mouse.down();
    await page.mouse.move(p.x + p.dx, p.y + p.dy, { steps: 6 });
    await page.mouse.up();
    const after = await values();
    expect(after[handle as keyof typeof after]).not.toBeCloseTo(
      before[handle as keyof typeof before],
      2,
    );
    for (const fixed of ['heading', 'tilt', 'distance'] as const)
      if (fixed !== handle) expect(after[fixed]).toBeCloseTo(before[fixed], 4);
  }
  for (const [i, handle] of ['fov-bottom', 'fov-right', 'fov-top', 'fov-left'].entries()) {
    const before = (await page.evaluate('window.viewshedHarness.state.items[0]')) as {
      horizontalFov: number;
      verticalFov: number;
      observer: unknown;
      target: unknown;
    };
    const drag = (await page.evaluate(`(async()=>{
      const {frustumCorners,frame,add,scale}=await import('/src/features/map/viewshed/math.ts');
      const {handleAxis}=await import('/src/features/map/viewshed/manipulators.ts');
      const v=window.viewshedHarness.state.items[0],c=frustumCorners(v),p=scale(add(c[${i}],c[${(i + 1) % 4}]),.5);
      const q=add(p,scale(handleAxis(v,'${handle}'),${i === 0 || i === 3 ? -8 : 8}));
      const project=p=>{const g=frame(v.observer).toGeo(p);return window.viewshedHarness.project(g.longitude,g.latitude,g.elevationMeters);};
      return {a:project(p),b:project(q)};
    })()`)) as { a: { x: number; y: number }; b: { x: number; y: number } };
    await page.mouse.move(drag.a.x, drag.a.y);
    await page.mouse.down();
    await page.mouse.move(drag.b.x, drag.b.y, { steps: 6 });
    await page.mouse.up();
    const property = i % 2 ? 'horizontalFov' : 'verticalFov';
    await expect
      .poll(() => page.evaluate(`window.viewshedHarness.state.items[0].${property}`))
      .toBeGreaterThan(before[property]);
    expect(await page.evaluate('window.viewshedHarness.state.items[0].target')).toEqual(
      before.target,
    );
    expect(await page.evaluate('window.viewshedHarness.state.items[0].observer')).toEqual(
      before.observer,
    );
  }
  await expect(page.getByLabel('Heading (°)', { exact: true })).not.toBeVisible();
  await page.getByText('Adjust view', { exact: true }).click();
  await expect(page.getByLabel('Heading (°)', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/viewshed-controls.png' });
});
