import { expect, test } from '@playwright/test';

test('draw area, analyze real API, toggle scenarios, change assumptions and recover from errors', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://tiles.goong.io/**', route => route.fulfill({ json: { version:8,sources:{},
    layers:[{id:'background',type:'background',paint:{'background-color':'#e2ebe7'}}] } }));
  await page.route('**/api/v1/layers', route => route.fulfill({ json: { layers: [] } }));
  const rect = (w:number,s:number,e:number,n:number) => ({type:'Polygon',coordinates:[[[w,s],[e,s],[e,n],[w,n],[w,s]]]});
  const created = await (await request.post('/api/v1/zoning/plans', { data:{name:`Indicators ${Date.now()}`,study_area:rect(106.76,10.82,106.763,10.823)} })).json();
  const saved = await request.post(`/api/v1/zoning/plans/${created.id}/commands`, { data:{revision:created.revision,
    scenario_id:created.scenarios[1].id,action:'save_building',payload:{parcel_id:'3885881',name:'Indicator building',
      geometry:rect(106.7607,10.8207,106.761,10.821),floors:2,floor_height:3.2,space_use_id:'residential',
      floor_overrides:[{floor:1,floor_height:4,space_use_id:'office',counts_gfa:true,counts_far:true}]}} });
  expect(saved.ok()).toBe(true);
  const plan = await saved.json();
  await page.goto('/tests/browser/data-layers.html');
  await page.getByRole('button',{name:'Indicators',exact:true}).click();
  await expect(page.getByRole('complementary',{name:'Indicators panel'})).toBeVisible();
  await page.getByRole('button',{name:'Draw area',exact:true}).click();
  await page.evaluate(() => window.dataMap.jumpTo({center:[106.762,10.822],zoom:16}));
  const points = [[106.761,10.821],[106.762,10.821],[106.762,10.822],[106.761,10.822]];
  for (const coord of points) {
    const point = await page.evaluate(coord => { const p=window.dataMap.project(coord as [number,number]);return {x:p.x,y:p.y}; },coord);
    await page.mouse.click(point.x,point.y);
  }
  await page.getByRole('button',{name:'Analyze area',exact:true}).click();
  await expect(page.getByRole('table').filter({hasText:'Estimated capacity & demand'})).toBeVisible();
  await expect(page.getByRole('region',{name:'Current land use',exact:true})).toContainText('ODT');
  await expect(page.getByRole('region',{name:'Current land use',exact:true})).toContainText('TMD');
  await expect(page.getByRole('region',{name:'Transit accessibility'})).toContainText('75%');
  await page.getByRole('combobox',{name:'Plan',exact:true}).selectOption(plan.id);
  const panel = page.getByRole('complementary',{name:'Plan details'});
  await expect(panel.getByRole('columnheader',{name:'Proposed',exact:true})).toBeVisible();
  const populationRow=panel.getByRole('row').filter({has:page.getByRole('rowheader',{name:'Population people',exact:true})});
  const oldPopulation=await populationRow.locator('td').last().innerText();
  await panel.getByLabel('Include plan scenario').uncheck();
  await expect(panel.getByRole('columnheader',{name:'Proposed',exact:true})).toHaveCount(0);
  expect(await page.evaluate(() => window.dataMap.getStyle().sources['development-scene'].data.features.length)).toBe(0);
  await panel.getByLabel('Include plan scenario').check();
  await expect(panel.getByRole('columnheader',{name:'Proposed',exact:true})).toBeVisible();
  await expect(populationRow.locator('td').last()).toHaveText(oldPopulation);
  await panel.getByText('Assumptions',{exact:true}).click();
  await panel.getByLabel('Residential m² / person',{exact:true}).fill('70');
  await panel.getByRole('button',{name:'Apply assumptions'}).click();
  await expect(populationRow.locator('td').last()).not.toHaveText(oldPopulation);
  await panel.getByText('Assumptions',{exact:true}).click();
  for (const width of [1440,1024,768,320]) {
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path:`../.runtime/indicators/indicators-${width}.png`});
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.getByRole('button',{name:'Existing',exact:true}).click();
  await expect(panel.getByRole('columnheader',{name:'Proposed',exact:true})).toHaveCount(0);
  await page.route('**/api/v1/indicators/area', route => route.fulfill({status:503,json:{detail:'Analytics unavailable'}}));
  await page.getByRole('button',{name:'Scenario A',exact:true}).click();
  await expect(panel.getByRole('alert')).toContainText('Analytics unavailable');
  await page.unroute('**/api/v1/indicators/area');
  await panel.getByRole('button',{name:'Retry',exact:true}).click();
  await expect(panel.getByRole('columnheader',{name:'Proposed',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Close plan',exact:true}).click();
  await page.getByRole('button',{name:'Close zoning workspace',exact:true}).click();
  expect(await page.evaluate(() => window.dataMap.getSource('zoning-editor'))).toBeUndefined();
  expect(errors).toEqual([]);
});
