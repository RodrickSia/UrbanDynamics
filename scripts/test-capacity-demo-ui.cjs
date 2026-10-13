// Headless regression of this repository's own demo; does not control user browser tabs.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'test-results','demo-capacity');
const modulePath=process.env.PLANNING_PLAYWRIGHT_MODULE||path.join(root,'..','UrbanDynamics','.runtime','ui-check','node_modules','playwright-core');
const {chromium}=require(modulePath);
(async()=>{
 const report=JSON.parse(fs.readFileSync(path.join(out,'http-execution.json'),'utf8'));assert.equal(report.status,'passed');
 const browser=await chromium.launch({channel:'msedge',headless:true});const errors=[];
 try{
  const page=await browser.newPage({viewport:{width:1450,height:1000}});page.on('pageerror',e=>errors.push(e.message));
  await page.goto(report.screening_url);await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Hoàn thành và lưu'));
  await page.selectOption('#option','together_3');
  assert.match(await page.locator('#source').textContent(),/NỀN\/CAPACITY GIẢ LẬP/);
  assert.match(await page.locator('#capacities').textContent(),/synthetic/);
  assert.equal(await page.locator('#assumption-case option').count(),7);
  await page.locator('#results').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'screening-reference.png'),fullPage:false});
  await page.selectOption('#assumption-case','capacity_minus20');assert.match(await page.locator('#capacities').textContent(),/Vượt capacity/);
  await page.screenshot({path:path.join(out,'capacity-minus20.png'),fullPage:false});
  await page.goto(report.native_url+'&view=sumo');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Hoàn thành và lưu'));
  assert.equal(await page.locator('#traffic-seed option').count(),3);
  assert((await page.locator('#sumo-metrics tbody tr').count())>=6);
  assert(!/Chưa có lượt SUMO/.test(await page.locator('#sumo-summary').textContent()));
  await page.locator('#sumo-results').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'native-three-seeds.png'),fullPage:false});
  // Verify parcel -> building plan -> explicit package -> prepared study.
  await page.goto(report.screening_url.split('?')[0]);await page.waitForFunction(()=>!document.querySelector('#system-demo').hidden);
  await page.locator('#system-demo summary').first().click();
  const study=JSON.parse(fs.readFileSync(path.join(out,'study.json'),'utf8'));
  await page.selectOption('#system-snapshot',study.system_snapshot_id);await page.click('#system-load');
  await page.waitForFunction(()=>document.querySelector('#system-parcels').options.length>0);
  await page.selectOption('#system-parcels',Object.values(study.system_parcel_bindings));
  await page.selectOption('#system-background','synthetic_capacity_v1');await page.check('#system-sensitivity');await page.selectOption('#system-sensitivity-engine','screening');await page.click('#system-prepare');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Bước 3'));
  const prepared=JSON.parse(await page.locator('#input').inputValue());assert.equal(prepared.background_snapshot.id,'synthetic_capacity_v1');assert.equal(prepared.uncertainty.engine,'screening');
  assert.equal(prepared.projects.length,3);assert.equal(errors.length,0,errors.join('\n'));
  fs.writeFileSync(path.join(out,'ui-report.json'),JSON.stringify({status:'passed',checks:['saved sensitivity case and provenance','capacity threshold changes','native three seeds and SUMO table','parcel/building/package preparation'],errors},null,2));
  console.log('UI: 4 groups passed');
 }finally{await browser.close();}
})().catch(e=>{fs.writeFileSync(path.join(out,'ui-report.json'),JSON.stringify({status:'failed',error:e.message}));console.error(e.message);process.exitCode=1;});
