import { expect, test } from '@playwright/test';
import fixture from './cost-fixture.json' with { type: 'json' };

test.beforeEach(async ({page}) => {
  await page.route('**/api/v1/indicators/area', route => route.fulfill({status:503,json:{detail:'Test indicators unavailable'}}));
  await page.route('**/api/v1/zoning/plans/*/costs?*', route => {
    const existing = new URL(route.request().url()).searchParams.get('scenario_id') !== fixture.report.scenario_id;
    return route.fulfill({json:existing ? {...fixture.report,buildings:[],demolitions:[],total:0,known_total:0,construction:0,demolition:0} : fixture.report});
  });
  await page.goto('/tests/browser/construction-costs.html');
  await page.getByRole('button',{name:'Construction costs',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Construction budget'})).toBeVisible();
});

test('saves a building-specific quote through the selected scenario command', async ({page}) => {
  await page.getByText('Budget assumptions',{exact:true}).first().click();
  await page.getByLabel('Apply construction settings to').selectOption('house');
  await page.getByLabel('Custom building quote').check();
  await page.getByLabel('Construction package').selectOption('mid');
  const request = page.waitForRequest('**/api/v1/zoning/plans/cost-plan/commands');
  await page.route('**/api/v1/zoning/plans/cost-plan/commands', route => route.fulfill({json:{...fixture.plan,revision:2}}));
  await page.getByRole('button',{name:'Save budget'}).click();
  const body = (await request).postDataJSON();
  expect(body).toMatchObject({revision:1,scenario_id:'cost-proposal',action:'save_cost_settings',payload:{building_overrides:{house:{unit_price:6000000}}}});
  await expect(page.getByText('Estimated plan cost')).toBeVisible();
  await page.getByRole('button',{name:'Change scenario'}).click();
  await expect(page.getByText(/Existing buildings are retained/)).toBeVisible();
  await page.getByText('Budget assumptions',{exact:true}).first().click();
  await expect(page.getByLabel('Construction package')).toBeDisabled();
});

test('shows missing demolition as incomplete and retries API failures', async ({page}) => {
  await page.route('**/api/v1/zoning/plans/*/costs?*', route => route.fulfill({status:503,json:{detail:'Storage unavailable'}}));
  await page.getByRole('button',{name:'Construction costs',exact:true}).click();
  await page.getByRole('button',{name:'Construction costs',exact:true}).click();
  await expect(page.getByRole('alert').filter({hasText:'Storage unavailable'})).toBeVisible();
  await page.route('**/api/v1/zoning/plans/*/costs?*', route => route.fulfill({json:{...fixture.report,total:null,demolition:null,warnings:['Enter a demolition rate in VND/m².']}}));
  await page.getByRole('button',{name:'Retry budget'}).click();
  await expect(page.getByText('Known costs · incomplete')).toBeVisible();
  await expect(page.getByRole('definition').filter({hasText:'Unknown'})).toBeVisible();
  await page.getByRole('button',{name:'Switch panel'}).click();
  await expect(page.getByRole('heading',{name:'Construction budget'})).toHaveCount(0);
  await expect(page.getByText('Test indicators unavailable')).toBeVisible();
});

test('offers automatic demolition and saves editable rate and height assumptions', async ({page}) => {
  await page.route('**/api/v1/zoning/plans/*/costs?*', route => route.fulfill({json:{...fixture.report,
    demolition_default_rate:200000,demolition_rate:200000,demolition_area_m2:240,
    settings:{...fixture.report.settings,demolition_rate:null,demolition_area_m2:null,demolition_floor_height_m:3.2}}}));
  const toggle=page.getByRole('button',{name:'Construction costs',exact:true});
  await toggle.click();await toggle.click();
  await page.getByText('Budget assumptions',{exact:true}).first().click();
  await page.locator('.cost-settings summary').filter({hasText:/^Demolition$/}).click();
  await expect(page.getByRole('combobox',{name:'Demolition area',exact:true})).toHaveValue('auto');
  await expect(page.getByLabel('Demolition (VND/m²)',{exact:true})).toHaveValue('200000');
  await page.getByRole('combobox',{name:'Demolition area',exact:true}).selectOption('custom');
  await expect(page.getByLabel('Total demolition floor area (m²)',{exact:true})).toHaveValue('240');
  await page.getByRole('combobox',{name:'Demolition area',exact:true}).selectOption('auto');
  await page.getByLabel('Demolition (VND/m²)',{exact:true}).fill('300000');
  await page.getByRole('button',{name:/Reset to/}).click();
  await expect(page.getByLabel('Demolition (VND/m²)',{exact:true})).toHaveValue('200000');
  await page.getByLabel('Demolition (VND/m²)',{exact:true}).fill('250000');
  await page.getByLabel('Estimated floor height (m)',{exact:true}).fill('4');
  await page.screenshot({path:'test-results/demolition-settings.png'});
  await page.route('**/api/v1/zoning/plans/cost-plan/commands', route => route.fulfill({json:{...fixture.plan,revision:2}}));
  const request=page.waitForRequest('**/api/v1/zoning/plans/cost-plan/commands');
  await page.getByRole('button',{name:'Save budget'}).click();
  expect((await request).postDataJSON().payload).toMatchObject({demolition_rate:250000,demolition_area_m2:null,demolition_floor_height_m:4});
});

for (const width of [320,768,1024,1440]) test(`budget fits ${width}px with stable toolbar and no console errors`, async ({page}) => {
  const errors:string[]=[];
  page.on('pageerror',error => errors.push(error.message));
  await page.setViewportSize({width,height:900});
  const money = page.getByRole('button',{name:'Construction costs',exact:true});
  const before = await money.boundingBox();
  await money.click();await money.click();
  const after = await money.boundingBox();
  expect(after?.x).toBe(before?.x);
  await page.getByText('Budget assumptions',{exact:true}).first().click();
  await expect(page.getByLabel('Construction package')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path:`test-results/costs-${width}.png`,fullPage:true});
  expect(errors).toEqual([]);
});
