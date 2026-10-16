const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const root=path.resolve(__dirname,'..'),req=createRequire(path.join(root,'frontend/package.json'));
const {chromium}=req('@playwright/test');
const out=path.join(root,'test-results/general-agent');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1280,height:900}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let release;const gate=new Promise(resolve=>{release=resolve;});let sends=0;
 try{
  await page.route('**/api/v1/agent/chat',async route=>{
   const body=route.request().postDataJSON();sends++;
   if(sends===2){await route.fulfill({status:503,json:{detail:'Test response unavailable'}});return;}
   await gate;
   const stored=await (await page.request.get('http://127.0.0.1:8192/api/v1/agent/sessions/'+body.session_id)).json();
   await route.fulfill({json:{...stored,messages:[{role:'user',content:body.message},{role:'assistant',content:'Your study area is ready to inspect.'}],trace:[]}});
  });
  await page.goto('http://127.0.0.1:8192/',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Planning assistant',exact:true}).click();
  const panel=page.getByRole('complementary',{name:'Planning assistant'});
  const input=panel.getByLabel('Message to planning assistant');
  const prompt='Show my current study area.';
  await input.fill(prompt);
  await panel.getByRole('button',{name:'Send',exact:true}).click();
  const bubble=panel.locator('article[data-role="user"]').filter({hasText:prompt});
  await bubble.waitFor();
  const thinking=panel.getByRole('status').filter({hasText:'Model is thinking…'});
  await thinking.waitFor();
  if(await panel.locator('.assistant-welcome').count())throw Error('Welcome suggestions should hide after sending');
  if(await input.inputValue()!==''||!await input.isDisabled())throw Error('Composer must clear and disable while waiting');
  if(await bubble.count()!==1)throw Error('Pending message duplicated');
  await page.screenshot({path:path.join(out,'chat-thinking.png'),fullPage:true});
  release();
  await panel.getByText('Your study area is ready to inspect.',{exact:true}).waitFor();
  if(await thinking.count()!==0||await bubble.count()!==1)throw Error('Response must replace pending state without duplicating the user message');
  const retry='Retryable example question.';
  await input.fill(retry);await input.press('Enter');
  await panel.getByText('No response received. Retry this message or refresh.',{exact:true}).waitFor();
  if(await input.inputValue()!==retry||await thinking.count()!==0)throw Error('Failure must preserve retry text and stop thinking');
  if(errors.length)throw Error(errors.join('; '));
  const result={passed:true,checks:['message_visible_before_response','thinking_below_message','composer_cleared_and_disabled','no_duplicate_after_response','failure_preserves_message_and_retry','no_page_errors'],model_calls:0};
  fs.writeFileSync(path.join(out,'chat-feedback-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{release();await browser.close();}
})().catch(e=>{console.error(String(e));process.exit(1);});
