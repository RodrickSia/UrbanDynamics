const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const root=path.resolve(__dirname,'..'),req=createRequire(path.join(root,'frontend/package.json'));
const {chromium}=req('@playwright/test');
const out=path.join(root,'test-results/general-agent');
(async()=>{
 const evidence=JSON.parse(fs.readFileSync(path.join(out,'structured-query-result.json'),'utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.addInitScript(id=>localStorage.setItem('development-assistant-session',id),evidence.model_session_id);
  await page.goto('http://127.0.0.1:8192/',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Planning assistant',exact:true}).click();
  const panel=page.getByRole('complementary',{name:'Planning assistant'});
  await panel.getByText('Filtered dataset results',{exact:true}).waitFor();
  await panel.getByRole('columnheader',{name:'price.geometry_reviewed',exact:true}).waitFor();
  const result=evidence.turns.at(-1).response.structured_queries.at(-1);
  if(!result.returned)throw Error('Positive source-backed model query required');
  const last=await page.request.get(`http://127.0.0.1:8192/api/v1/agent/sessions/${evidence.model_session_id}`);
  const session=await last.json();
  if(session.query_features.features.length!==result.returned)throw Error('Filtered geometry count mismatch');
  if(session.structured_queries.length>5)throw Error('Query history exceeded five entries');
  await panel.getByText('Filtered dataset results',{exact:true}).scrollIntoViewIfNeeded();
  await page.waitForTimeout(3000);
  await page.screenshot({path:path.join(out,'structured-query-desktop.png'),fullPage:true});
  const dl=page.waitForEvent('download');
  await panel.getByRole('button',{name:'Download evidence report'}).click();
  const download=await dl;await download.saveAs(path.join(out,'structured-query-export.md'));
  const report=fs.readFileSync(path.join(out,'structured-query-export.md'),'utf8');
  if(!report.includes(result.id)||!report.includes('geometry_reviewed'))throw Error('Export lost query/provenance');
  await page.setViewportSize({width:390,height:844});
  await panel.getByText('Filtered dataset results',{exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(out,'structured-query-mobile.png'),fullPage:true});
  if(errors.length)throw Error(errors.join('; '));
  const summary={passed:true,rows:result.returned,checks:['filtered_table','price_review_flags','matching_map_geometry','bounded_history','source_backed_export','mobile_panel','no_page_errors']};
  fs.writeFileSync(path.join(out,'structured-browser-result.json'),JSON.stringify(summary,null,2));console.log(JSON.stringify(summary));
 }finally{await browser.close();}
})().catch(e=>{console.error(String(e));process.exit(1);});
