import { expect, test } from '@playwright/test';
import { GeoJSONVT } from '@maplibre/geojson-vt';
import { fromGeojsonVt } from '@maplibre/vt-pbf';

test.beforeEach(async ({ page }) => {
  const tiles = new GeoJSONVT({ type: 'Feature', properties: { class: 'street', structure: 'road' },
    geometry: { type: 'LineString', coordinates: [[106.7,10.79],[106.7,10.81]] },
  }, { maxZoom: 17 });
  await page.route('**/metric-road-tiles/**', route => {
    const [z,x,y] = new URL(route.request().url()).pathname.match(/\d+/g)!.map(Number);
    return route.fulfill({ body: Buffer.from(fromGeojsonVt({ streets: tiles.getTile(z,x,y) ?? { features: [] } })) });
  });
  const images = await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 512;
    const context = canvas.getContext('2d')!;
    context.fillStyle = 'rgb(128,80,0)'; context.fillRect(0, 0, 512, 512);
    const dem = canvas.toDataURL().split(',')[1];
    context.fillStyle = '#334450'; context.fillRect(0, 0, 512, 512);
    return { dem, satellite: canvas.toDataURL().split(',')[1] };
  });
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: {
    version: 8,
    sources: {
      roads: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
      composite: { type: 'vector', tiles: ['http://127.0.0.1:5173/metric-road-tiles/{z}/{x}/{y}.pbf'], maxzoom: 17 },
    },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': '#233440' } },
      { id: 'provider-road', type: 'line', source: 'roads', paint: { 'line-width': 4, 'line-color': '#ccddee' } },
      { id: 'road-street', type: 'line', source: 'composite', 'source-layer': 'streets',
        paint: { 'line-width': 18, 'line-color': '#ccddee' } },
    ],
  } }));
  await page.route('https://satellite.goong.io/**', route => route.fulfill({ contentType: 'image/png', body: Buffer.from(images.satellite, 'base64') }));
  await page.route('https://tiles.mapterhorn.com/**', route => route.request().url().endsWith('tilejson.json')
    ? route.fulfill({ json: { tilejson: '3.0.0', tiles: ['https://tiles.mapterhorn.com/{z}/{x}/{y}.webp'] } })
    : route.fulfill({ contentType: 'image/png', body: Buffer.from(images.dem, 'base64') }));
  await page.goto('/tests/browser/workspace.html');
  await page.waitForFunction('window.workspace?.map()?.isStyleLoaded()');
  await page.evaluate('window.workspace.map().jumpTo({center:[106.7,10.8],zoom:17})');
  await page.evaluate('window.workspace.mode("3d")');
  await page.waitForFunction('!window.workspace.map().isMoving() && window.workspace.map().queryTerrainElevation([106.7,10.8]) === 80');
});

test('3D preview and fixed anchors survive satellite and standard style swaps', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.mouse.click(500, 450);
  const anchors = await page.evaluate('window.workspace.state().points');
  expect(anchors).toHaveLength(1);
  await page.evaluate('window.workspace.map().jumpTo({bearing:20,pitch:48})');
  const animations = await page.evaluate('window.workspace.animations()');
  for (const style of ['satellite', 'standard', 'satellite', 'standard']) {
    await page.evaluate(`window.workspace.style('${style}')`);
    await page.waitForFunction(`Boolean(window.workspace.map().getLayer('${style === 'satellite' ? 'satellite-imagery' : 'background'}')) && window.workspace.map().isStyleLoaded() && !window.workspace.map().isMoving()`);
    await page.mouse.move(550, 480);
    await expect.poll(() => page.evaluate('window.workspace.state().preview !== null')).toBe(true);
    await expect.poll(async () => {
      const png = await page.screenshot({ clip: { x: 543, y: 473, width: 14, height: 14 } });
      const count = await page.evaluate(async base64 => {
        const image = new Image(); image.src = `data:image/png;base64,${base64}`; await image.decode();
        const canvas = document.createElement('canvas'); canvas.width = canvas.height = 14;
        const context = canvas.getContext('2d')!; context.drawImage(image, 0, 0);
        const data = context.getImageData(0, 0, 14, 14).data;
        let count = 0;
        for (let i = 0; i < data.length; i += 4) if (data[i] > 130 && data[i + 1] < 110 && data[i + 2] < 80) count++;
        return count;
      }, png.toString('base64'));
      return count;
    }, { timeout: 15000 }).toBeGreaterThan(5);
    expect(await page.evaluate('window.workspace.state().points')).toEqual(anchors);
    expect(await page.evaluate('window.workspace.map().getPitch()')).toBeCloseTo(48);
    expect(await page.evaluate('window.workspace.map().getBearing()')).toBeCloseTo(20);
    expect(await page.evaluate('window.workspace.animations()')).toBe(animations);
    await page.mouse.move(560, 490);
  }
  expect(errors).toEqual([]);
});

test('mode changes preserve provider roads and use a single monotonic camera flight', async ({ page }) => {
  await page.evaluate('window.workspace.mode("2d")');
  await page.waitForFunction('window.workspace.map().getPitch() === 0 && !window.workspace.map().isMoving()');
  // Control animation time independently of SwiftShader throughput. This
  // checks camera continuity, not hardware FPS or remote tile latency.
  await page.clock.install();
  await page.clock.pauseAt(new Date(Date.now() + 1000));
  const before = await page.evaluate('window.workspace.animations()');
  await page.evaluate(`window.flightPitches = []; window.workspace.map().on('render', () => window.flightPitches.push(window.workspace.map().getPitch())); window.workspace.mode('3d')`);
  await page.clock.runFor(1000);
  await page.clock.resume();
  await page.waitForFunction('window.workspace.map().getPitch() === 60 && !window.workspace.map().isMoving()');
  expect(await page.evaluate('window.workspace.animations()')).toBe(before + 1);
  const pitches = await page.evaluate('window.flightPitches') as number[];
  expect(pitches.filter(pitch => pitch > 0 && pitch < 60).length).toBeGreaterThan(1);
  expect(pitches.every((pitch, index) => index === 0 || pitch >= pitches[index - 1])).toBe(true);
  expect(await page.evaluate('window.workspace.map().getStyle().layers.find(l => l.id === "provider-road").paint'))
    .toEqual({ 'line-width': 4, 'line-color': '#ccddee' });
  expect(await page.evaluate('window.workspace.map().getStyle().layers.some(l => l.id.startsWith("urban-road"))')).toBe(false);
});

test('opacity updates do not restart the camera flight or reset bearing', async ({ page }) => {
  await page.evaluate('window.workspace.map().jumpTo({bearing:35,pitch:48})');
  const before = await page.evaluate('window.workspace.animations()');
  await page.evaluate('window.workspace.opacity(0.65)');
  await page.waitForTimeout(750);
  expect(await page.evaluate('window.workspace.animations()')).toBe(before);
  expect(await page.evaluate('window.workspace.map().getBearing()')).toBeCloseTo(35);
  expect(await page.evaluate('window.workspace.map().getPitch()')).toBeCloseTo(48);
});

test('plain road retains seven-metre width through fractional zoom, terrain and mode swaps', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  for (const mode of ['3d', '2d']) {
    await page.evaluate(`window.workspace.mode('${mode}')`);
    await page.waitForFunction(`!window.workspace.map().isMoving() && window.workspace.map().getPitch() === ${mode === '3d' ? 60 : 0}`);
    for (const zoom of [18.8, 19.1, 20.05]) {
      await page.evaluate(`window.workspace.map().jumpTo({zoom:${zoom},pitch:${mode === '3d' ? 65 : 0}})`);
      await page.waitForFunction('window.workspace.map().areTilesLoaded()');
      const png = await page.screenshot();
      const widths = await page.evaluate(async ({ base64, altitude }) => {
        const image = new Image(); image.src = `data:image/png;base64,${base64}`; await image.decode();
        const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
        const ctx = canvas.getContext('2d')!; ctx.drawImage(image, 0, 0);
        const h = (window as unknown as { workspace: {
          map(): { unproject(p: number[]): { lat: number } };
          project(lng: number, lat: number, altitude: number): { x: number; y: number };
        } }).workspace;
        return [180,350,530].map(y => {
          const latitude = h.map().unproject([500,y]).lat;
          const delta = 3.5 / (6371008.8 * Math.PI / 180 * Math.cos(latitude * Math.PI / 180));
          const left = h.project(106.7 - delta, latitude, altitude);
          const right = h.project(106.7 + delta, latitude, altitude);
          const data = ctx.getImageData(0,y,canvas.width,1).data;
          const xs: number[] = [];
          for (let x=0; x<canvas.width; x++) if (Math.abs(data[x*4]-204)<5 && Math.abs(data[x*4+1]-221)<5 && Math.abs(data[x*4+2]-238)<5) xs.push(x);
          return { expected: right.x-left.x, actual: (xs.at(-1) ?? 0)-(xs[0] ?? 0)+1 };
        });
      }, { base64: png.toString('base64'), altitude: mode === '3d' ? 80 : 0 });
      for (const width of widths) expect(Math.abs(width.actual-width.expected), JSON.stringify({mode,zoom,...width})).toBeLessThan(3);
    }
  }
  const paint = await page.evaluate('window.workspace.map().getPaintProperty("road-street", "line-color")');
  expect(paint).toBe('#ccddee');
  expect(await page.evaluate('window.workspace.map().getPaintProperty("road-street", "line-pattern")')).toBeUndefined();
  expect(await page.evaluate('window.workspace.map().getPaintProperty("road-street", "line-dasharray")')).toBeUndefined();
  expect(errors).toEqual([]);
});

test('completed area survives basemap reloads with the same vertices and labels', async ({ page }) => {
  await page.evaluate(`window.workspace.measurement({kind:'area',status:'complete',preview:null,points:
    [[106.6995,10.7995],[106.7005,10.7995],[106.7005,10.8005],[106.6995,10.8005]].map(([longitude,latitude],i)=>({
      id:String(i),longitude,latitude,elevationMeters:80,elevationAvailable:true,surface:'terrain'
    }))})`);
  await expect(page.locator('[data-area-label]')).toHaveCount(2);
  const state = await page.evaluate('window.workspace.state()');
  const labels = await page.locator('[data-area-label]').allTextContents();
  for (const style of ['satellite','standard']) {
    await page.evaluate(`window.workspace.style('${style}')`);
    await page.waitForFunction(`Boolean(window.workspace.map().getLayer('${style === 'satellite' ? 'satellite-imagery' : 'background'}')) && window.workspace.map().isStyleLoaded()`);
    await expect(page.locator('[data-area-label="area"]')).toBeVisible();
    expect(await page.evaluate('window.workspace.state()')).toEqual(state);
    expect(await page.locator('[data-area-label]').allTextContents()).toEqual(labels);
    await page.screenshot({path:`test-results/area-${style}.png`});
  }
});

test('area controls work with keyboard, reduced motion and a narrow viewport', async ({ page }) => {
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.locator('.map-canvas canvas')).toBeVisible();
  const tools = page.getByRole('button',{name:'Measurement tools'});
  await tools.focus(); await page.keyboard.press('Enter');
  await expect(page.getByRole('group',{name:'Choose measurement'})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(tools).toBeFocused();
  await expect(tools).toHaveAttribute('aria-expanded','false');
  await tools.click();
  await page.getByRole('button',{name:'Measure area',exact:true}).click();
  const toolbar = page.getByRole('region',{name:'Area measurement'});
  await expect(toolbar).toBeVisible();
  await expect(toolbar.getByRole('button',{name:'Done',exact:true})).toBeDisabled();
  const bounds = await toolbar.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(390);
  for (const button of await toolbar.getByRole('button').all()) {
    const box = await button.boundingBox();
    expect(box!.x+box!.width).toBeLessThanOrEqual(390);
    expect(box!.y+box!.height).toBeLessThanOrEqual(844);
    const icon = await button.locator('svg').boundingBox();
    expect(icon!.x).toBeGreaterThanOrEqual(box!.x);
    expect(icon!.x+icon!.width).toBeLessThanOrEqual(box!.x+box!.width);
  }
  await page.screenshot({path:'test-results/area-mobile-controls.png'});
  await toolbar.getByRole('button',{name:'Clear measurement'}).click();
  await tools.click(); await page.getByRole('button',{name:'Measure distance',exact:true}).click();
  await expect(page.getByRole('region',{name:'Distance measurement'})).toBeVisible();
});
