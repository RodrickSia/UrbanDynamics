import { expect, test } from '@playwright/test';

test('planning buttons match map controls and slide below expanded search', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: {
    version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#cbdcd7' } }],
  } }));
  await page.route('https://satellite.goong.io/**', route => route.fulfill({ contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK1cAAAAASUVORK5CYII=', 'base64') }));
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [] } }));
  await page.route('**/api/v1/zoning/plans', route => route.fulfill({ json: { plans: [] } }));
  await page.goto('/tests/browser/data-layers.html');

  const nav = page.getByRole('navigation', { name: 'Planning workspace' });
  const plans = nav.getByRole('button', { name: 'Plans' });
  const indicators = nav.getByRole('button', { name: 'Indicators' });
  const rightControl = page.getByRole('button', { name: 'Zoom in' });
  const search = page.getByRole('searchbox', { name: 'Search places' });

  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const closed = await nav.boundingBox();
    const sizes = await page.evaluate(() => {
      const plansBox = document.querySelector<HTMLButtonElement>('.zoning-nav-button')!.getBoundingClientRect();
      const indicatorsBox = document.querySelector<HTMLButtonElement>('.zoning-nav-button + .zoning-nav-button')!.getBoundingClientRect();
      const rightBox = document.querySelector<HTMLButtonElement>('.navigation-buttons button')!.getBoundingClientRect();
      return { planWidth: plansBox.width, planHeight: plansBox.height, indicatorX: indicatorsBox.x,
        indicatorY: indicatorsBox.y, planX: plansBox.x, planBottom: plansBox.bottom, rightWidth: rightBox.width,
        rightHeight: rightBox.height };
    });
    expect(closed).toBeTruthy();
    expect(sizes.planWidth).toBe(sizes.rightWidth);
    expect(sizes.planHeight).toBe(sizes.rightHeight);
    expect(sizes.indicatorX).toBe(sizes.planX);
    expect(sizes.indicatorY).toBe(sizes.planBottom);

    await search.click();
    const searchPanel = page.getByRole('region', { name: 'Search workspace' });
    await expect(searchPanel).toBeVisible();
    await expect(nav).toHaveAttribute('data-search-open', 'true');
    await expect.poll(async () => {
      const panelBox = await searchPanel.boundingBox();
      const navBox = await nav.boundingBox();
      return !!panelBox && !!navBox && navBox.y >= panelBox.y + panelBox.height + 8;
    }).toBe(true);
    expect((await nav.boundingBox())!.y).toBeGreaterThan(closed!.y);
    await expect(plans).toBeInViewport();
    await expect(indicators).toBeInViewport();
    await page.screenshot({ path: `test-results/zoning-navigation-search-${width}.png` });

    await rightControl.click();
    await expect(searchPanel).toHaveCount(0);
    await expect(nav).toHaveAttribute('data-search-open', 'false');
    await expect.poll(async () => Math.round((await nav.boundingBox())!.y)).toBe(width < 768 ? 76 : 80);
  }
  await page.setViewportSize({ width: 320, height: 900 });
  await plans.click();
  const planPanel = page.getByLabel('Plans panel');
  await expect(planPanel).toBeVisible();
  await expect.poll(async () => {
    const navBox = await nav.boundingBox();
    const panelBox = await planPanel.boundingBox();
    return !!navBox && !!panelBox && panelBox.y >= navBox.y + navBox.height;
  }).toBe(true);
  expect(errors).toEqual([]);
});
