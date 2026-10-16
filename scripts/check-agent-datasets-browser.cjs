const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const root=path.resolve(__dirname,'..'),req=createRequire(path.join(root,'frontend/package.json'));
const {chromium}=req('@playwright/test');
const out=path.join(root,'test-results/general-agent');
(async()=>{
 const live=JSON.parse(fs.readFileSync(path.join(out,'datasets-result.json'),'utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.addInitScript(id=>localStorage.setItem('development-assistant-session',id),live.session_id);
  await page.goto('http://127.0.0.1:8192/',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Planning assistant',exact:true}).click();
  const panel=page.getByRole('complementary',{name:'Planning assistant'});
  await panel.getByText('Dataset evidence',{exact:true}).waitFor();
  await panel.getByText('Amenities near candidate sites',{exact:true}).waitFor();
  await page.getByText('Map ready',{exact:true}).waitFor({timeout:45000});
  await page.waitForTimeout(2000);
  await panel.getByText('Amenities near candidate sites',{exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(out,'datasets-desktop.png'),fullPage:true});
  // Exercise form handling without paying for another model turn.
  const session=await (await page.request.get('http://127.0.0.1:8192/api/v1/agent/sessions/'+live.session_id)).json();
  let sends=0,lastMessage='',lastWorkspace;
  await page.route('**/api/v1/agent/chat',async route=>{
   sends++;const body=route.request().postDataJSON();lastMessage=body.message;lastWorkspace=body.workspace;
   await new Promise(resolve=>setTimeout(resolve,200));
   await route.fulfill({json:{...session,messages:[...session.messages,{role:'user',content:lastMessage},{role:'assistant',content:'Keyboard test received.'}],trace:[]}});
  });
  const input=panel.getByLabel('Message to planning assistant');
  await input.fill('Line one');
  await input.press('Shift+Enter');
  if(await input.inputValue()!=='Line one\n'||sends!==0)throw Error('Shift+Enter must insert a newline without sending');
  await input.evaluate(el=>el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true,isComposing:true})));
  if(sends!==0)throw Error('IME composition must not submit');
  await input.press('Enter');
  await panel.getByText('Keyboard test received.',{exact:true}).waitFor();
  if(sends!==1||lastMessage.trim()!=='Line one')throw Error('Enter did not submit exactly once');
  if(!lastWorkspace?.map_pois?.features?.length)throw Error('Existing system POI vector source was not passed into chat');
  const poiResponse=await page.request.post(`http://127.0.0.1:8192/api/v1/agent/sessions/${live.session_id}/tools/layer_query`,{
   data:{workspace:lastWorkspace,arguments:{layer:'poi',radius_m:0}}});
  if(!poiResponse.ok())throw Error('System POIs failed backend binding: '+await poiResponse.text());
  const poiData=await poiResponse.json();
  if(!poiData.tool_result.records.length)throw Error('No system POI records returned');
  const poiEvidence={workspace:lastWorkspace,result:poiData.tool_result};
  fs.writeFileSync(path.join(out,'system-pois-browser.json'),JSON.stringify(poiEvidence,null,2));
  if(errors.length)throw Error(errors.join('; '));
  const result={passed:true,checks:['price_dataset_evidence','amenity_source_evidence','enter_sends_once','shift_enter_newline','ime_enter_does_not_send','system_map_pois_in_chat','system_pois_queryable','no_page_errors']};
  fs.writeFileSync(path.join(out,'datasets-browser-result.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(String(e));process.exit(1);});
