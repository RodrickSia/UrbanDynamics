import { expect, test } from '@playwright/test';

for (const width of [320, 768, 1024, 1440]) {
  test(`data layer panel matches the workspace at ${width}px and works with keyboard`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route('https://tiles.goong.io/**', (route) =>
      route.fulfill({
        json: {
          version: 8,
          sources: {},
          layers: [
            { id: 'background', type: 'background', paint: { 'background-color': '#cdded9' } },
          ],
        },
      }),
    );
    await page.route('**/api/v1/**', (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/api/v1/population')
        return route.fulfill({
          json: {
            available: true,
            years: Array.from({ length: 16 }, (_, i) => ({ year: 2015 + i })),
          },
        });
      if (path === '/api/v1/layers')
        return route.fulfill({
          json: {
            layers: ['flood_history', 'flood_satellite', 'flood_risk'].map((id) => ({
              id,
              available: true,
            })),
          },
        });
      return route.fulfill({ status: 204 });
    });
    await page.goto('/tests/browser/data-layers.html');
    await page.getByRole('button', { name: 'Open data layers', exact: true }).click();
    const panel = page.getByRole('region', { name: 'Data layers' });
    await expect(panel.getByText('4 available')).toBeVisible();
    await expect(panel.getByText('WorldPop · 16 years')).toHaveCount(0);
    await expect(panel.getByText('Ready', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('checkbox', { name: 'Rain' })).toHaveCount(0);
    const population = panel.getByRole('checkbox', { name: 'Population', exact: true });
    await population.focus();
    await page.keyboard.press('Space');
    await expect(population).toBeChecked();
    const year = panel.getByRole('combobox', { name: 'Population year' });
    await year.selectOption('2024');
    await panel.getByRole('combobox', { name: 'Population palette' }).selectOption('fire');
    await expect(panel.getByText('1 active')).toBeVisible();
    const row = panel
      .locator('.dataset-row')
      .filter({ has: page.getByRole('checkbox', { name: 'Population', exact: true }) });
    const iconBox = await row.locator('.dataset-row-icon').boundingBox();
    const nameBox = await row.locator('.layer-copy').boundingBox();
    expect(nameBox!.x - iconBox!.x).toBeLessThan(60);
    expect(nameBox!.x).toBeGreaterThan(iconBox!.x);
    const heading = panel.getByRole('heading', { name: 'Data layers', exact: true });
    await expect(heading).toBeInViewport();
    if (width <= 900)
      await expect(page.getByRole('searchbox', { name: 'Search places' })).toHaveCount(0);
    const opacity = panel.getByRole('slider', { name: 'Population opacity' });
    await opacity.focus();
    await page.keyboard.press('ArrowLeft');
    await expect(opacity).toHaveValue('75');
    expect(await panel.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(
      true,
    );
    expect(
      await panel
        .locator('.dataset-panel-body')
        .evaluate((element) => element.scrollWidth <= element.clientWidth),
    ).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`layers-${width}.png`) });
    await panel.getByRole('checkbox', { name: 'Points of interest' }).uncheck();
    await expect(panel.getByRole('checkbox', { name: 'Points of interest' })).not.toBeChecked();
    await panel.getByRole('button', { name: 'Close data layers' }).click();
    await expect(panel).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}
