// Automated regression of our local app; no third-party browser actions.
const {chromium}=require('../.runtime/ui-check/node_modules/playwright-core');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
  const out=process.env.PLANNING_EVIDENCE_DIR||'test-results/planning-system-multisite';
  const native=JSON.parse(fs.readFileSync(out+'/http-report.json','utf8'));
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const checks=[];
  try{
    const page=await browser.newPage({viewport:{width:1360,height:980}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(native.url);
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Hoàn thành và lưu'));
    assert.equal(await page.locator('#option').inputValue(),'together_3');
    assert.equal(await page.locator('#study-mode').inputValue(),'cumulative');
    checks.push('Direct link restores saved three-parcel native result and chosen option');
    if (fs.existsSync(out+'/context-handoff-report.json')) {
      await page.locator('#layer').selectOption('school');
      assert.match(await page.locator('#map-note').textContent(), /OSM/);
      assert.match(await page.locator('#map-note').textContent(), /chưa xác nhận chỗ học/);
      assert.ok(await page.locator('#map polyline').count()>0);
      await page.locator('#layer').selectOption('shadow');
      assert.match(await page.locator('#map-note').textContent(), /chưa phải nhiệt độ/);
      checks.push('OSM school access renders without implying enrollment, and shade is labelled separately from temperature');
    }
    await page.locator('#system-load').click();
    await page.waitForFunction(()=>document.querySelector('#system-parcels').options.length===200);
    await page.locator('#system-floors').fill('4');
    for(const id of native.parcel_ids)await page.locator(`#system-parcel-map path[data-parcel="${id}"]`).dispatchEvent('click');
    assert.equal(await page.locator('#system-parcels').evaluate(el=>el.selectedOptions.length),3);
    await page.locator(`#system-parcel-map path[data-parcel="${native.parcel_ids[0]}"]`).dispatchEvent('click');
    assert.equal(await page.locator('#system-parcels').evaluate(el=>el.selectedOptions.length),2);
    await page.locator(`#system-parcel-map path[data-parcel="${native.parcel_ids[0]}"]`).dispatchEvent('click');
    assert.equal(await page.locator('#system-programs tbody tr').count(),3);
    await page.locator('#system-prepare').click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Đã nối parcel'));
    let study=JSON.parse(await page.locator('#input').inputValue());
    assert.equal(study.comparison_policy,'equal_program');
    assert.ok(study.projects.every(p=>p.development.buildings[0].gross_floor_area_m2===1600));
    checks.push('Polygon clicks toggle multiple selections and preserve equal declared GFA');
    await page.locator('#system-mode').selectOption('cumulative');
    await page.locator('#system-prepare').click();
    await page.waitForFunction(()=>JSON.parse(document.querySelector('#input').value).mode==='cumulative');
    study=JSON.parse(await page.locator('#input').inputValue());
    assert.equal(study.options.length,5);assert.equal(study.phases.length,3);
    await page.locator('#preflight').click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Sẵn sàng:'));
    checks.push('Cumulative builder creates individual/joint scenarios and development phases');
    await page.locator('#system-group-parcels').evaluate(el=>el.closest('details').open=true);
    await page.locator('#system-group-parcels').selectOption([native.parcel_ids[0],native.parcel_ids[2]]);
    await page.locator('#system-add-scenario').click();
    await page.waitForFunction(()=>document.querySelector('#system-counting').options.length>=4);
    if(native.counting_reference_id)await page.locator('#system-counting').selectOption(native.counting_reference_id);
    await page.locator('#system-prepare').click();
    await page.waitForFunction(()=>JSON.parse(document.querySelector('#input').value).options.length===1);
    study=JSON.parse(await page.locator('#input').inputValue());
    assert.equal(study.options[0].active_project_ids.length,2);
    if(native.counting_reference_id){assert.equal(study.traffic_prior.counting_reference_id,native.counting_reference_id);assert.equal(study.traffic_prior.source_kind,'synthetic');assert.equal(study.traffic_prior.cars[18]+study.traffic_prior.motorcycles[18],3888);}
    checks.push('Custom joint scenario and optional counting-derived vehicle-mix prior');
    await page.locator('#system-demo').screenshot({path:out+'/multisite-builder.png'});
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
    assert.deepEqual(errors,[]);
    checks.push('Mobile layout and no JavaScript errors');
    fs.writeFileSync(out+'/ui-report.json',JSON.stringify({status:'passed',checks},null,2));
    console.log(JSON.stringify({status:'passed',checks},null,2));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
