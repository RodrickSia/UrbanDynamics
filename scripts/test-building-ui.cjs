// Optional browser check: install playwright-core in the ignored .runtime/ui-check directory.
// This creates synthetic scenario runs in the running local stack.
const {chromium} = require('../.runtime/ui-check/node_modules/playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

process.chdir(path.resolve(__dirname, '..'));
fs.mkdirSync('test-results', {recursive:true});

(async () => {
  const channel = process.env.BUILDING_BROWSER_CHANNEL || 'msedge';
  const report = {checks: [], browser: `${channel}, headless`, base: process.env.BUILDING_API_URL || 'http://127.0.0.1:8001'};
  const browser = await chromium.launch({channel, headless:true});
  try {
    const context = await browser.newContext({viewport:{width:1360,height:1000}});
    await context.route('https://tile.openstreetmap.org/**', route => route.abort());
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${report.base}/simulation`, {waitUntil:'domcontentloaded'});
    await page.locator('#demo').click();
    await page.locator('#status').filter({hasText:'Đã nạp ví dụ'}).waitFor();
    await page.locator('#ack').check();
    await page.locator('#run').click();
    await page.locator('#results').waitFor({state:'visible'});
    let saved = await page.evaluate(() => result);
    assert.equal(saved.assessment_level,'uncalibrated_screening');
    assert.equal(await page.locator('#mitigated-roof').count(),0);
    assert.deepEqual(Object.keys(saved.variants),['baseline','development']);
    assert.equal(saved.impact_assessment.verdict,'worse');
    assert.equal(saved.variants.development.peak_vehicle_trips_per_hour,80);
    assert.equal(await page.locator('#metrics tr').count(),12);
    report.checks.push('two-input prediction: traffic/utilities and impact assessment; no improved design input');
    await page.locator('#recommend').click();
    await page.locator('#suggestions .suggestion').first().waitFor();
    saved = await page.evaluate(() => result);
    assert.ok(saved.recommendations.length);
    assert.equal(saved.recommendation_status,'partial_improvement');
    assert.ok(saved.recommendations[0].predicted.unretained_runoff_m3 < saved.variants.development.unretained_runoff_m3);
    assert.ok(Math.abs(saved.recommendations[0].predicted.peak_vehicle_trips_per_hour-60)<1e-7);
    assert.equal(saved.recommendations[0].design.users,saved.inputs.development.users);
    report.checks.push('generated improvements obey constraints, preserve building and report unmet runoff goal');

    await page.locator('#results').scrollIntoViewIfNeeded();
    await page.screenshot({path:'test-results/building-ui-desktop.png',fullPage:true});
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#download').click();
    const download = await downloadPromise;
    await download.saveAs('test-results/building-ui-export.json');
    assert.deepEqual(JSON.parse(fs.readFileSync('test-results/building-ui-export.json','utf8')),saved);
    report.checks.push('downloaded JSON matches saved API result');

    const reopened = await context.newPage();
    await reopened.goto(`${report.base}/simulation?run=${saved.id}`,{waitUntil:'domcontentloaded'});
    await reopened.locator('#results').waitFor({state:'visible'});
    assert.deepEqual(await reopened.evaluate(() => result),saved);
    assert.equal(await reopened.locator('#rain').inputValue(),String(saved.inputs.rainfall_mm));
    assert.equal(await reopened.locator('#title').inputValue(),saved.inputs.title);
    assert.equal(await reopened.locator('#budget').inputValue(),String(saved.recommendation_constraints.budget_vnd));
    report.checks.push('saved link reopens identical result');

    await page.locator('#rain').fill('100');
    assert.equal(await page.locator('#results').isVisible(),false);
    await page.locator('#run').click();
    await page.locator('#results').waitFor({state:'visible'});
    const changed = await page.evaluate(() => result);
    assert.notEqual(changed.id,saved.id);
    assert.notEqual(changed.input_sha256,saved.input_sha256);
    assert.equal(changed.inputs.rainfall_mm,100);
    report.checks.push('editing hides stale result; rerun gets new ID and input digest');

    await page.locator('#development-green').fill('11');
    await page.locator('#run').click();
    await page.locator('#status.error').waitFor();
    assert.match(await page.locator('#status').innerText(),/100%/);
    report.checks.push('invalid surface totals are rejected in UI');
    await page.locator('#development-green').fill('10');

    const mapAvailable = await page.evaluate(() => typeof L !== 'undefined');
    if (mapAvailable) {
      // Use actual pointer clicks to exercise site polygon drawing, then footprint drawing.
      await page.locator('#draw-target').selectOption('site');
      await page.locator('#draw').click();
      const box = await page.locator('#map').boundingBox();
      for (const [x,y] of [[.35,.25],[.65,.25],[.65,.75],[.35,.75]])
        await page.mouse.click(box.x+box.width*x,box.y+box.height*y);
      await page.locator('#finish').click();
      await page.locator('#status').filter({hasText:'Đã nhận polygon'}).waitFor();
      await page.locator('#draw-target').selectOption('development');
      await page.locator('#draw').click();
      const footprintBox = await page.locator('#map').boundingBox();
      for (const [x,y] of [[.47,.4],[.53,.4],[.53,.6],[.47,.6]])
        await page.mouse.click(footprintBox.x+footprintBox.width*x,footprintBox.y+footprintBox.height*y);
      await page.locator('#finish').click();
      await page.locator('#status').filter({hasText:'Đã nhận polygon'}).waitFor();
      await page.locator('#run').click();
      await page.locator('#results').waitFor({state:'visible'});
      assert.ok((await page.evaluate(() => result)).inputs.development.footprint);
      report.checks.push('pointer drawing: site and contained building footprint, then successful run');
    } else report.checks.push('Leaflet unavailable; map drawing not checked');

    await page.setViewportSize({width:390,height:844});
    await page.locator('#results').scrollIntoViewIfNeeded();
    await page.screenshot({path:'test-results/building-ui-mobile.png',fullPage:true});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    report.checks.push('mobile viewport has no document-wide horizontal overflow');

    const offlineContext = await browser.newContext({viewport:{width:1200,height:900}});
    await offlineContext.route('https://unpkg.com/**',route=>route.abort());
    const offlinePage = await offlineContext.newPage();
    offlinePage.on('pageerror',error=>errors.push(error.message));
    await offlinePage.goto(`${report.base}/simulation`,{waitUntil:'domcontentloaded'});
    await offlinePage.locator('#demo').click();
    await offlinePage.locator('#status').filter({hasText:'Đã nạp ví dụ'}).waitFor();
    await offlinePage.locator('#ack').check();
    await offlinePage.locator('#run').click();
    await offlinePage.locator('#results').waitFor({state:'visible'});
    report.checks.push('blocked CDN: example and calculation work without map library');
    assert.deepEqual(errors,[]);
    report.checks.push('no uncaught JavaScript errors');
    report.status='passed';
  } catch(error) {report.status='failed'; report.error=error.message; process.exitCode=1;}
  finally {
    await browser.close();
    fs.writeFileSync('test-results/building-ui-report.json',JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  }
})();
