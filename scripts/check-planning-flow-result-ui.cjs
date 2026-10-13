const {chromium}=require('../.runtime/ui-check/node_modules/playwright-core');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=path.resolve(__dirname,'../test-results/planning-flow-default');
(async()=>{
 const report=JSON.parse(fs.readFileSync(out+'/http-report.json','utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 let page;
 const errors=[];
 try{
  page=await browser.newPage({viewport:{width:1400,height:1100}});
  page.setDefaultTimeout(30000);page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(/\/jobs\/|\/runs\//.test(r.url()))console.log('API response '+r.status()+' '+r.url().split('/').slice(-2).join('/'));});
  console.log('Browser started');
  await page.goto(report.url);
  console.log('Page loaded');
  await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Hoàn thành và lưu'));
  assert.equal(await page.locator('#option').inputValue(),'together_3');
  const study=JSON.parse(await page.locator('#input').inputValue());
  assert.equal(study.traffic_prior.cars[18]+study.traffic_prior.motorcycles[18],3888);
  const row=label=>page.locator('#sumo-metrics tbody tr').filter({has:page.locator('td:first-child',{hasText:label})});
  assert.equal(await row('Xe nền giả định: ô tô + xe máy').locator('td').nth(2).textContent(),'3.888');
  assert.equal(await row('Xe dự kiến trong giờ').locator('td').nth(2).textContent(),'3.909');
  assert.equal(await row('Xe hoàn thành').locator('td').nth(1).textContent(),'3.019');
  assert.equal(await row('Xe hoàn thành').locator('td').nth(2).textContent(),'3.909');
  assert.equal(await row('Tồn đọng cuối lượt').locator('td').nth(2).textContent(),'0');
  assert.equal(await row('Hàng chờ tối đa').locator('td').nth(2).textContent(),'41,61');
  assert.match(await page.locator('#sumo-summary').textContent(),/19 lượt/);
  assert.match(await page.locator('#metrics tbody tr').filter({hasText:'Delay mọi xe hoàn thành'}).textContent(),/Chưa biết/);
  await page.locator('#option').selectOption('P1_only');
  assert.equal(await row('Tồn đọng cuối lượt').locator('td').nth(2).textContent(),'1.113');
  await page.locator('#option').selectOption('P3_only');
  assert.equal(await row('Tồn đọng cuối lượt').locator('td').nth(2).textContent(),'436');
  await page.locator('#sumo-results').screenshot({path:out+'/sumo-raw-table.png'});
  await page.locator('#option').selectOption('baseline');
  assert.equal(await row('Xe dự kiến trong giờ').locator('td').nth(2).textContent(),'3.888');
  assert.equal(await row('Tồn đọng cuối lượt').locator('td').nth(2).textContent(),'869');
  await page.locator('#option').selectOption('P3_only');
  await page.locator('#layer').selectOption('roads');
  await page.locator('#map').screenshot({path:out+'/p3-traffic-map.png'});
  await page.screenshot({path:out+'/saved-result.png',fullPage:true});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(out+'/saved-result-ui-report.json',JSON.stringify({status:'passed',url:report.url,checks:['Saved native deep link restores together_3','3888 flow and 3909 planned/completed vehicles shown','P1/P3/baseline backlog changes with selection','Queue and zero backlog preserved','Saved counting source shown','Comparison remains insufficient_data','P3 traffic layer renders','No page errors']},null,2));
  console.log('Saved native result and P3 traffic map verified');
 }catch(e){
  console.error(JSON.stringify({error:e.message,status:page?await page.locator('#status').textContent():null,errors}));
  if(page)await page.screenshot({path:out+'/saved-result-failure.png'});
  throw e;
 }finally{await browser.close()}
})().catch(e=>{console.error(e.message);process.exitCode=1});
