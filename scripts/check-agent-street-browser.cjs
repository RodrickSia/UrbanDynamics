const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const root=path.resolve(__dirname,'..'),req=createRequire(path.join(root,'frontend/package.json'));
const {chromium}=req('@playwright/test');
const out=path.join(root,'test-results/general-agent');
(async()=>{
 const evidence=JSON.parse(fs.readFileSync(path.join(out,'street-search-result.json'),'utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.addInitScript(id=>localStorage.setItem('development-assistant-session',id),evidence.model_session_id);
  await page.goto('http://127.0.0.1:8192/',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Planning assistant',exact:true}).click();
  const panel=page.getByRole('complementary',{name:'Planning assistant'});
  await panel.getByText(/Analysis area: Hẻm 114 Trần Quốc Tuấn/).waitFor();
  const answer=evidence.turns.at(-1).response.answer;
  await panel.locator('article[data-role="assistant"]').last().waitFor();
  if(!answer.includes('?'))throw Error('Saved last turn must ask to confirm search scope');
  await page.waitForTimeout(4000);
  await page.screenshot({path:path.join(out,'street-scope-desktop.png'),fullPage:true});
  if(errors.length)throw Error(errors.join('; '));
  const result={passed:true,checks:['saved_named_street_scope_visible','restored_scope_question','no_page_errors']};
  fs.writeFileSync(path.join(out,'street-browser-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(String(e));process.exit(1);});
