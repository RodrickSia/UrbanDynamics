import { expect, test } from '@playwright/test';

test('real Vietnam terrain loads at street zoom and retains mountain relief', async ({ page }) => {
  const failures: string[] = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.hostname === 'tiles.mapterhorn.com' && response.status() >= 400) failures.push(`${response.status()} ${url.pathname}`);
  });
  await page.goto('/tests/browser/measurement.html?live=1');
  await page.waitForFunction('window.harness?.map.isStyleLoaded() && window.harness.map.isSourceLoaded("urban-terrain-dem")');
  await expect.poll(() => page.evaluate('window.harness.map.queryTerrainElevation([106.7,10.8])'), { timeout: 40000 }).toBeGreaterThan(0);
  await page.evaluate('window.harness.map.jumpTo({center:[103.8,22.3], zoom:12, pitch:65})');
  await expect.poll(() => page.evaluate('window.harness.map.queryTerrainElevation([103.8,22.3])'), { timeout: 40000 }).toBeGreaterThan(500);
  await page.waitForFunction('window.harness.map.areTilesLoaded()');
  expect(failures).toEqual([]);
  await page.screenshot({ path: 'test-results/vietnam-terrain-live.png' });
});

test('application loads the configured basemap and measurement UI in 3D', async ({ page }) => {
  const requests: string[] = [];
  page.on('requestfailed', (request) => {
    const url = new URL(request.url());
    if (url.hostname.endsWith('goong.io')) requests.push(`FAILED ${url.hostname}${url.pathname} ${request.failure()?.errorText}`);
  });
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.hostname.endsWith('goong.io')) requests.push(`${response.status()} ${url.hostname}${url.pathname}`);
  });
  await page.goto('/');
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  await expect.poll(async () => ({
    ready: (await page.locator('[aria-live="polite"]').allTextContents()).some((text) => text.includes('Goong map is ready')),
    failed: requests.filter((request) => !request.startsWith('200')),
  }), { timeout: 45000 }).toEqual({ ready: true, failed: [] });
  await expect.poll(() => requests.filter((request) => /\d+\/\d+\/\d+/.test(request)), { timeout: 45000 }).not.toHaveLength(0);
  await page.getByRole('searchbox', { name: 'Search places' }).click();
  await page.getByRole('button', { name: 'Hanoi, Vietnam', exact: true }).click();
  await page.getByRole('button', { name: 'Close place details' }).click();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click({ clickCount: 3, delay: 400 });
  await page.getByRole('button', { name: 'Switch to 3D' }).click();
  await page.getByRole('button', { name: 'Measure distance', exact: true }).click();
  await page.mouse.move(550, 350);
  await expect(page.getByRole('region', { name: 'Distance measurement' })).toBeVisible();
  await page.mouse.click(550, 350);
  await page.mouse.move(650, 440);
  await expect(page.getByRole('button', { name: 'Done', exact: true })).toBeDisabled();
  await page.mouse.click(650, 440);
  await expect(page.getByRole('button', { name: 'Done', exact: true })).toBeEnabled();
  await expect(page.locator('.measurement-distance-pill')).toHaveCount(1);
  await expect(page.locator('.measurement-distance-pill')).toBeVisible();
  await expect(page.getByRole('region', { name: 'Distance measurement' })).not.toContainText('3D total');
  await test.info().attach('map-network', { body: JSON.stringify(requests, null, 2), contentType: 'application/json' });
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: 'test-results/application-measurement-live.png' });
});
