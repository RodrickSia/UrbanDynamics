const fs=require('fs');
const path=require('path');
const {createRequire}=require('module');
const root=path.resolve(__dirname,'..');
const req=createRequire(path.join(root,'frontend/package.json'));
const {chromium}=req('@playwright/test');
const out=path.join(root,'test-results/development-agent');

(async()=>{
 const live=JSON.parse(fs.readFileSync(path.join(out,'live-result.json'),'utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.addInitScript(id=>localStorage.setItem('development-assistant-session',id),live.session_id);
  await page.goto('http://127.0.0.1:8192/',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Plans',exact:true}).click();
  await page.getByRole('button',{name:/^Agent integration check · Development/}).click();
  await page.getByRole('button',{name:'Development',exact:true}).click();
  await page.getByRole('button',{name:'Planning assistant',exact:true}).click();
  const panel=page.getByRole('complementary',{name:'Planning assistant'});
  await panel.getByText('Agent integration check · Development',{exact:true}).waitFor();
  await panel.getByText('Saved simulation runs',{exact:true}).waitFor();
  if(process.env.AGENT_UI_CHAT==='1'){
    await panel.getByLabel('Message to planning assistant').fill('Use workspace_read to explain the currently selected plan, scenario and its building floor count. Do not edit or start a job. Keep the answer brief.');
    const responsePromise=page.waitForResponse(r=>r.url().endsWith('/api/v1/agent/chat')&&r.request().method()==='POST',{timeout:120000});
    await panel.getByRole('button',{name:'Send',exact:true}).click();
    const response=await responsePromise;
    const payload=response.request().postDataJSON(),reply=await response.json();
    if(!response.ok()||payload.workspace.plan_id!==live.test_plan_id||!reply.trace.some(t=>t.tool==='workspace_read'&&t.status==='succeeded'))throw Error('Browser chat failed to send current verified workspace');
    fs.writeFileSync(path.join(out,'browser-chat.json'),JSON.stringify({workspace:payload.workspace,trace:reply.trace,answer:reply.answer},null,2));
  }
  const id=Object.keys(live.live_model.development_runs).at(-1);
  await panel.getByLabel('Assistant simulation run').selectOption(id);
  await panel.getByText('Full result and sources',{exact:true}).waitFor({timeout:30000});
  await panel.locator('th').filter({hasText:/Before/}).first().waitFor();
  await panel.getByText('Full result and sources',{exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(out,'assistant-desktop.png'),fullPage:true});
  const font=await panel.evaluate(el=>({panel:getComputedStyle(el).fontFamily,body:getComputedStyle(document.body).fontFamily}));
  if(font.panel!==font.body)throw Error('Assistant font differs from map body');
  await page.reload({waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Planning assistant',exact:true}).click();
  await page.getByRole('complementary',{name:'Planning assistant'}).getByText('Saved simulation runs',{exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(out,'assistant-mobile.png'),fullPage:true});
  const bounds=await page.getByRole('complementary',{name:'Planning assistant'}).boundingBox();
  if(bounds.x<0||bounds.x+bounds.width>391)throw Error('Assistant panel overflows mobile viewport');
  if(errors.length)throw Error(errors.join('; '));
  const result={passed:true,checks:['current_plan_context','restored_chat','saved_run_polling','before_after_table','font_matches','reload_session','mobile_fit','no_page_errors'],font};
  fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(String(e));process.exit(1);});
