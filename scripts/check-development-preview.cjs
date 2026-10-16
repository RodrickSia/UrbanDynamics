const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const { chromium } = require('../frontend/node_modules/@playwright/test');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'test-results', 'development-context');
const record = JSON.parse(fs.readFileSync(path.join(out, 'live-native.json'), 'utf8'));

(async () => {
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];
  const mapResponses={};
  page.on('response',response=>{
    const host=new URL(response.url()).hostname;
    if(host.endsWith('goong.io')){const key=host+' '+response.status();mapResponses[key]=(mapResponses[key]??0)+1;}
  });
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(record.url,{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Plans',exact:true}).click({timeout:30000});
  await page.locator('.zoning-plan-list li > button:first-child').filter({hasText:record.plan.name}).first().click();
  await page.getByRole('button',{name:'Development',exact:true}).click();
  await page.locator('.development-list button').filter({hasText:'Apartment proposal'}).first().click();
  const panel=page.getByRole('region',{name:'Development simulation',exact:true});
  await panel.waitFor({state:'visible',timeout:20000});
  if(record.job?.status==='succeeded') await panel.getByRole('button',{name:'View last completed run',exact:true}).click();
  await page.waitForTimeout(3000);
  await page.screenshot({path:path.join(out,'web-desktop.png'),fullPage:true});
  const text=await panel.innerText();
  assert(text.includes('Quick estimate'));
  let hasResults=false;
  if(record.job?.status==='succeeded'){
    await panel.getByRole('heading',{name:'Building impact · before and after'}).waitFor({timeout:30000});
    assert(await panel.getByText('Before',{exact:true}).count()>=1);
    assert(await panel.getByText('After',{exact:true}).count()>=1);
    assert(await panel.getByText('Maximum queue length',{exact:false}).count()>=1);
    assert((await panel.innerText()).includes('OSM local extract'));
    assert(await panel.locator('.simulation-comparison').evaluateAll(tables=>tables.every(table=>table.scrollWidth<=table.parentElement.clientWidth+1)));
    hasResults=true;
    await panel.getByRole('heading',{name:'Building impact · before and after'}).scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(out,'web-results.png'),fullPage:true});
    await panel.getByRole('heading',{name:'Traffic · same background, added building trips'}).scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(out,'web-traffic.png'),fullPage:true});
    await page.reload({waitUntil:'domcontentloaded'});
    await page.getByRole('button',{name:'Plans',exact:true}).click();
    await page.locator('.zoning-plan-list li > button:first-child').filter({hasText:record.plan.name}).first().click();
    await page.getByRole('button',{name:'Development',exact:true}).click();
    await page.locator('.development-list button').filter({hasText:'Apartment proposal'}).first().click();
    await panel.getByRole('heading',{name:'Building impact · before and after'}).waitFor({timeout:30000});
  }
  await page.setViewportSize({width:390,height:844});
  await panel.scrollIntoViewIfNeeded();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  if(hasResults) assert(await panel.locator('.simulation-comparison').evaluateAll(tables=>tables.every(table=>table.scrollWidth<=table.parentElement.clientWidth+1)));
  await page.screenshot({path:path.join(out,'web-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify({passed:true,hasResults,restoredAfterReload:hasResults,pageErrors:errors,mapResponses,plan:record.plan.id,url:record.url},null,2));
  await browser.close();
  console.log(JSON.stringify({passed:true,hasResults}));
})().catch(e=>{fs.writeFileSync(path.join(out,'browser-error.txt'),String(e.stack));process.exitCode=1;});
