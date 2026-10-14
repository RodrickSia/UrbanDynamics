const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'test-results','submission-features');
const {chromium}=require(process.env.PLANNING_PLAYWRIGHT_MODULE||path.join(root,'..','UrbanDynamics','.runtime','ui-check','node_modules','playwright-core'));
(async()=>{const report=JSON.parse(fs.readFileSync(path.join(out,'execution.json'),'utf8'));assert.equal(report.status,'passed');const browser=await chromium.launch({channel:'msedge',headless:true});const errors=[];try{
 const page=await browser.newPage({viewport:{width:1450,height:1050}});page.on('pageerror',e=>errors.push(e.message));
 await page.goto(report.screening_url);await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Hoàn thành và lưu'));
 assert.equal(await page.locator('#option option').count(),2); // baseline + one project.
 assert.match(await page.locator('#vietnam-note').textContent(),/80 L/);
 assert.equal(await page.locator('#vietnam-table tbody tr').count(),7);
 assert.match(await page.locator('#vietnam-density').textContent(),/500 m/);
 await page.locator('#vietnam-requirements').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'qcvn-requirements.png'),fullPage:false});
 await page.selectOption('#option','baseline');assert(await page.locator('#vietnam-requirements').isVisible());
 await page.goto(report.native_url);await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Hoàn thành và lưu'));
 assert.equal(await page.locator('#traffic-seed option').count(),3);assert((await page.locator('#sumo-metrics tbody tr').count())>=6);
 await page.locator('#sumo-results').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'grouped-native.png'),fullPage:false});
 await page.goto(report.screening_url.split('?')[0]);await page.waitForFunction(()=>!document.querySelector('#system-demo').hidden);await page.locator('#system-demo summary').first().click();
 await page.selectOption('#system-snapshot',report.snapshot_id);await page.click('#system-load');await page.waitForFunction(()=>document.querySelector('#system-parcels').options.length>0);
 await page.selectOption('#system-parcels',report.parcel_ids);await page.check('#system-merge-parcels');await page.check('#system-vietnam-catalog');await page.selectOption('#system-background','synthetic_capacity_v1');await page.uncheck('#system-sensitivity');await page.fill('#system-units','20');await page.fill('#system-residents','60');await page.fill('#system-floor-area','1600');await page.fill('#system-floors','4');await page.click('#system-prepare');
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Bước 3'));let input=JSON.parse(await page.locator('#input').inputValue());assert.equal(input.projects.length,1);assert.equal(input.projects[0].development.buildings[0].units,20);assert.equal(input.projects[0].development.buildings[0].residents,60);assert.equal(input.planning_catalog,'qcvn_urban_2021');assert.deepEqual(input.system_parcel_groups.P1,[...report.parcel_ids].sort());
 assert.equal(errors.length,0,errors.join('\n'));fs.writeFileSync(path.join(out,'ui-report.json'),JSON.stringify({status:'passed',checks:['QCVN panel and baseline switching','grouped OSM native three seeds','parcel selection to one building plan'],errors},null,2));console.log('UI: 3 groups passed');
 }finally{await browser.close();}
})().catch(error=>{fs.writeFileSync(path.join(out,'ui-report.json'),JSON.stringify({status:'failed',error:error.message}));console.error(error.message);process.exitCode=1;});
