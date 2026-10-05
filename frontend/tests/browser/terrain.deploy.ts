import { expect, test } from '@playwright/test';

test('deployed 3D map loads terrain through the production CSP', async ({ page }) => {
  const terrainFailures: string[] = [];
  let metadataLoaded = false;
  let tilesLoaded = 0;
  page.on('requestfailed', (request) => {
    const url = new URL(request.url());
    if (url.hostname === 'tiles.mapterhorn.com') {
      terrainFailures.push(`${url.pathname}: ${request.failure()?.errorText}`);
    }
  });
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.hostname !== 'tiles.mapterhorn.com') return;
    if (!response.ok()) terrainFailures.push(`${url.pathname}: HTTP ${response.status()}`);
    else if (url.pathname.endsWith('/tilejson.json')) metadataLoaded = true;
    else if (url.pathname.endsWith('.webp') || url.pathname.endsWith('.png')) tilesLoaded += 1;
  });

  const document = await page.goto('/');
  const policy = document?.headers()['content-security-policy'] ?? '';
  const connections = policy.split(';').find((directive) => directive.trim().startsWith('connect-src '));
  expect(connections, 'Production CSP must permit the DEM provider').toContain('https://tiles.mapterhorn.com');
  await expect(page.locator('.maplibregl-canvas')).toBeVisible();
  await page.getByRole('button', { name: 'Switch to 3D', exact: true }).click();
  await expect.poll(() => ({ metadataLoaded, hasTiles: tilesLoaded > 0, terrainFailures }), {
    timeout: 60000,
    message: 'Terrain metadata and image tiles should load without browser/network errors',
  }).toEqual({ metadataLoaded: true, hasTiles: true, terrainFailures: [] });
});
