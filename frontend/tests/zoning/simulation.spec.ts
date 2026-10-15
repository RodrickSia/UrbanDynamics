import { expect, test } from '@playwright/test';

test('saved per-floor development runs screening and native simulation, restores results and rejects stale revisions', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: {
    version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#dce5df' } }],
  } }));
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [] } }));
  const rect = (w: number, s: number, e: number, n: number) => ({ type: 'Polygon', coordinates: [[[w,s],[e,s],[e,n],[w,n],[w,s]]] });
  const created = await (await request.post('/api/v1/zoning/plans', { data: { name: `Simulation ${Date.now()}`, study_area: rect(106.76,10.82,106.763,10.823) } })).json();
  const response = await request.post(`/api/v1/zoning/plans/${created.id}/commands`, { data: {
    revision: created.revision, action: 'save_building', scenario_id: created.scenarios[1].id, payload: {
      parcel_id: '3885881', name: 'Mixed use', geometry: rect(106.7607,10.8207,106.761,10.821),
      floors: 2, floor_height: 3.2, space_use_id: 'residential', floor_overrides: [
        { floor: 1, floor_height: 4, space_use_id: 'commercial', counts_gfa: true, counts_far: true },
      ],
    },
  } });
  expect(response.ok()).toBe(true);
  const plan = await response.json();
  const open = async () => {
    await page.getByRole('button', { name: 'Plans', exact: true }).click();
    await page.locator('.zoning-plan-list li > button:first-child').filter({ hasText: plan.name }).click();
    await page.getByRole('button', { name: 'Development', exact: true }).click();
    await page.getByRole('combobox',{name:'Scope',exact:true}).selectOption('scenario');
  };
  await page.goto('/tests/browser/data-layers.html');
  await open();
  const simulation = page.getByRole('region', { name: 'Development simulation', exact: true });
  await simulation.getByRole('button', { name: 'Run simulation' }).click();
  await expect(simulation.getByRole('heading', { name: 'Building impact · before and after' })).toBeVisible({ timeout: 45000 });
  await expect(simulation.getByRole('row').filter({hasText:'Water'}).filter({hasText:'Unknown'}).first()).toBeVisible();
  const water = await simulation.getByRole('row', { name: /^Water / }).innerText();
  expect(water).toContain('Insufficient data');
  await page.reload(); await open();
  await expect(simulation.getByRole('heading', { name: 'Building impact · before and after' })).toBeVisible();
  await expect(simulation.getByRole('row', { name: /^Water / })).toHaveText(water, { useInnerText: true });
  await simulation.getByRole('combobox', { name: 'Scope', exact: true }).selectOption('parcel');
  await expect(simulation.getByRole('heading', { name: 'Building impact · before and after' })).toHaveCount(0);
  await expect(simulation.getByRole('button', { name: 'Run simulation' })).toBeDisabled();
  await simulation.getByRole('combobox', { name: 'Scope', exact: true }).selectOption('scenario');
  await expect(simulation.getByRole('heading', { name: 'Building impact · before and after' })).toBeVisible();
  await simulation.getByRole('combobox', { name: 'Engine', exact: true }).selectOption('native');
  await simulation.getByRole('button', { name: 'Run simulation' }).click();
  await expect(simulation.getByRole('heading', { name: 'Traffic · same background, added building trips' })).toBeVisible({ timeout: 60000 });
  for (const width of [1440,1024,768,320]) {
    await page.setViewportSize({ width, height: 900 });
    await simulation.getByRole('heading', { name: 'Building impact · before and after' }).scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `../.runtime/development/simulation-${width}.png` });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('button', { name: 'Existing', exact: true }).click();
  await expect(simulation).toHaveCount(0);
  await page.getByRole('button', { name: 'Scenario A', exact: true }).click();
  await page.getByRole('combobox',{name:'Scope',exact:true}).selectOption('scenario');
  await expect(simulation.getByRole('heading', { name: 'Building impact · before and after' })).toBeVisible();
  const saved = plan.scenarios[1].buildings[0];
  const edited = await request.post(`/api/v1/zoning/plans/${plan.id}/commands`, { data: {
    revision: plan.revision, action: 'save_building', scenario_id: plan.scenarios[1].id,
    payload: { id: saved.id, parcel_id: saved.parcel_id, name: saved.name, geometry: saved.geometry,
      floors: 1, floor_height: saved.floor_height, space_use_id: saved.space_use_id, floor_overrides: [] },
  } });
  expect(edited.ok()).toBe(true);
  await page.reload(); await open();
  await expect(simulation.getByRole('heading', { name: 'Building impact · before and after' })).toHaveCount(0);
  expect(errors).toEqual([]);
});
