// Smoke the merged main web without starting SUMO/SWMM or altering shared datasets.
const {chromium}=require('../frontend/node_modules/@playwright/test');
const fs=require('fs');
const path=require('path');
const base=process.env.MAIN_WEB_URL||'http://127.0.0.1:8173';
const out=path.resolve(__dirname,'../test-results/main-release');
async function main(){
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const checks=[];
  const errors=[];
  const mapResponses=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{const u=new URL(r.url());if(u.hostname.endsWith('.goong.io'))mapResponses.push({path:u.pathname,status:r.status()});});
  try{
    const response=await page.goto(base,{waitUntil:'domcontentloaded',timeout:60000});
    checks.push({name:'main frontend',ok:response.status()===200});
    const config=await page.request.get(base+'/api/v1/agent/config');
    const value=await config.json();
    checks.push({name:'agent configured',ok:config.ok()&&value.enabled&&value.model_configured,model:value.model});
    const button=page.getByRole('button',{name:/planning assistant|AI assistant|Open assistant/i});
    if(await button.count())await button.first().click();
    else {
      const labels=await page.getByRole('button').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('aria-label')).filter(Boolean));
      throw new Error('Agent button not found: '+JSON.stringify(labels));
    }
    await page.getByRole('complementary',{name:'Planning assistant'}).waitFor({state:'visible',timeout:20000});
    await page.locator('#assistant-message').waitFor({state:'visible'});
    checks.push({name:'agent UI',ok:true});
    await page.waitForTimeout(3000);
    await page.screenshot({path:path.join(out,'main-agent-desktop.png')});
    const viewport=[106.76,10.80,106.77,10.82];
    const created=await page.request.post(base+'/api/v1/agent/sessions',{data:{}});
    const session=await created.json();
    const sid=session.session_id;
    const tool=async(name,args)=>{
      const r=await page.request.post(base+`/api/v1/agent/sessions/${sid}/tools/${name}`,{data:{arguments:args,workspace:{viewport}},timeout:60000});
      const body=await r.json();return {status:r.status(),body};
    };
    const selected=await tool('area_select',{source:'viewport'});
    checks.push({name:'viewport scope',ok:selected.status===200});
    for(const layer of ['population','flood_risk','flood_history','flood_satellite','land_price','parcels','synthetic_buildings','traffic','sumo_network','sumo_simulation','poi']){
      const x=await tool('dataset_query',{query_json:JSON.stringify({layer,limit:2,aggregates:[{op:'count'}]})});
      checks.push({name:'dataset '+layer,ok:x.status===200,status:x.status,matched:x.body.tool_result?.matched_count,error:x.body.detail});
    }
    checks.push({name:'no browser runtime errors',ok:errors.length===0,errors});
    fs.writeFileSync(path.join(out,'main-map-network.json'),JSON.stringify(mapResponses,null,2));
    checks.push({name:'Goong map',ok:mapResponses.some(r=>r.status===200),responses:mapResponses.length,failed:mapResponses.filter(r=>r.status>=400).length});
    if(process.argv.includes('--model')){
      const prompt='Within the visible map, find parcels between 80 and 200 m². State the total matches, show only 2, and do not assume they are vacant. Respond in English.';
      const answer=page.waitForResponse(r=>r.url().endsWith('/api/v1/agent/chat')&&r.request().method()==='POST',{timeout:180000});
      await page.locator('#assistant-message').fill(prompt);
      await page.locator('#assistant-message').press('Enter');
      const r=await answer;
      const result=await r.json();
      fs.writeFileSync(path.join(out,'main-model.json'),JSON.stringify({prompt,status:r.status(),result},null,2));
      checks.push({name:'real model chat via Enter',ok:r.ok()&&result.messages?.at(-1)?.role==='assistant',status:r.status()});
      await page.screenshot({path:path.join(out,'main-agent-response.png')});
    }
    fs.writeFileSync(path.join(out,'main-smoke.json'),JSON.stringify(checks,null,2));
    console.log(JSON.stringify(checks));
    if(checks.some(x=>!x.ok))process.exitCode=1;
  }finally{await browser.close();}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
