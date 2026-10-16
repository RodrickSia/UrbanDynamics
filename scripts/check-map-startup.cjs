const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const root=path.resolve(__dirname,'..'),req=createRequire(path.join(root,'frontend/package.json'));
const {chromium}=req('@playwright/test');
const out=path.join(root,'test-results/general-agent');
const safe=value=>String(value).replace(/https?:\/\/[^\s"<>]+/g,url=>{try{const parsed=new URL(url);return parsed.origin+parsed.pathname;}catch{return '[URL]';}});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:900}});
 const forced=process.argv.includes('--force-goong-429');
 if(forced)await page.route('https://tiles.goong.io/**',route=>route.fulfill({status:429,contentType:'text/plain',body:'Rate limited for fallback regression'}));
 const events=[];
 let fallbackTiles=0;
 page.on('pageerror',e=>events.push({type:'pageerror',message:safe(e.message)}));
 page.on('console',m=>{if(m.type()==='error')events.push({type:'console',message:safe(m.text()).slice(0,400)});});
 page.on('response',r=>{if(r.status()===200&&r.url().startsWith('https://tile.openstreetmap.org/'))fallbackTiles++;if(r.status()>=400)events.push({type:'http',status:r.status(),url:safe(r.url())});});
 page.on('requestfailed',r=>events.push({type:'requestfailed',url:safe(r.url()),reason:r.failure()?.errorText}));
 try{
  await page.goto('http://127.0.0.1:8192/',{waitUntil:'domcontentloaded'});
  await page.waitForTimeout(7000);
  await page.screenshot({path:path.join(out,forced?'startup-forced-fallback.png':'startup-fresh.png'),fullPage:true});
  const initial={status:await page.locator('body').innerText(),events:[...events]};
  fs.writeFileSync(path.join(out,'startup-latest-network.json'),JSON.stringify({events,fallbackTiles,status:initial.status},null,2));
  if(forced){
   await page.getByText(/Goong is rate-limited\. Showing OpenStreetMap/).waitFor();
   if(!fallbackTiles)throw Error('Alternate basemap did not load any raster tiles');
   if(!await page.getByRole('link',{name:'OpenStreetMap contributors',exact:true}).count())throw Error('Missing map attribution');
  }
  await page.getByRole('button',{name:'Planning assistant',exact:true}).click();
  await page.getByRole('complementary',{name:'Planning assistant'}).waitFor();
  if(events.some(e=>e.type==='pageerror'))throw Error('Runtime error while opening the assistant');
  const evidence={passed:true,forced_429:forced,fallback_tiles_loaded:fallbackTiles,
    initial_status:initial.status.slice(-700),initial_events:initial.events};
  fs.writeFileSync(path.join(out,forced?'startup-fallback-result.json':'startup-result.json'),JSON.stringify(evidence,null,2));
  console.log(JSON.stringify(evidence));
 }finally{await browser.close();}
})().catch(e=>{console.error(safe(e));process.exit(1);});
