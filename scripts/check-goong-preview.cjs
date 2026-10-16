const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const root=path.resolve(__dirname,'..'),req=createRequire(path.join(root,'frontend/package.json'));
const {chromium}=req('@playwright/test');
const out=path.join(root,'test-results/general-agent');
(async()=>{
 const config=Object.fromEntries(fs.readFileSync(path.join(root,'.env.development-goong.local'),'utf8').trim().split(/\r?\n/).map(s=>s.split('=')));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[],mapResponses=[];let usesNewMapKey=false;
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',response=>{
  const url=new URL(response.url());
  if(url.hostname.endsWith('.goong.io')){
   mapResponses.push({host:url.hostname,path:url.pathname,status:response.status()});
   if(url.pathname.endsWith('goong_map_web.json')&&response.status()===200)usesNewMapKey=url.searchParams.get('api_key')===config.VITE_GOONG_MAPTILES_KEY;
  }
 });
 try{
  await page.goto('http://127.0.0.1:8192/',{waitUntil:'domcontentloaded'});
  const search=page.getByRole('searchbox',{name:'Search places'});
  await search.fill('hẻm 114 Trần Quốc Tuấn Gò Vấp');
  const match=page.getByRole('button',{name:/Hẻm 114 Trần Quốc Tuấn,/}).first();
  await match.waitFor({timeout:25000});
  await page.screenshot({path:path.join(out,'goong-search-suggestions.png')});
  await match.click();
  await page.getByRole('complementary',{name:'Place details'}).waitFor({timeout:25000});
  await page.waitForTimeout(3000);
  await page.screenshot({path:path.join(out,'goong-search-selected.png')});
  if(!usesNewMapKey)throw Error('Goong style did not load with the dedicated preview key');
  if(mapResponses.some(r=>r.status===429))throw Error('Goong still rate limited in fresh browser');
  if(errors.length)throw Error(errors.join('; '));
  const detail=await (await page.request.get('http://127.0.0.1:8192/api/v1/places/search?q='+encodeURIComponent('hẻm 114 Trần Quốc Tuấn Gò Vấp'))).json();
  const id=detail.results[0].id;
  const selected=await (await page.request.get('http://127.0.0.1:8192/api/v1/places/detail?place_id='+encodeURIComponent(id))).json();
  if(!(selected.longitude>106.68&&selected.longitude<106.70&&selected.latitude>10.81&&selected.latitude<10.83))throw Error('Unexpected place coordinates');
  const sid=(await (await page.request.post('http://127.0.0.1:8192/api/v1/agent/sessions',{data:{}})).json()).session_id;
  const tool=await page.request.post(`http://127.0.0.1:8192/api/v1/agent/sessions/${sid}/tools/area_select`,{data:{arguments:{source:'goong_place',query:'hẻm 114 Trần Quốc Tuấn Gò Vấp',match_index:0}}});
  const agent=await tool.json();
  if(!tool.ok()||!agent.tool_result.source.includes('Goong'))throw Error('Agent Goong place adapter failed');
  const html=await (await page.request.get('http://127.0.0.1:8192/')).text();
  const script=html.match(/src="([^"]+\.js)"/)[1];
  const bundle=await (await page.request.get('http://127.0.0.1:8192'+script)).text();
  if(bundle.includes(config.GOONG_REST_API_KEY))throw Error('Private REST key leaked into frontend bundle');
  const result={passed:true,usesNewMapKey,suggestions:detail.results.length,selected,agentSource:agent.tool_result.source,
   restKeyAbsentFromBundle:true,mapResponses,checks:['new_map_key','goong_suggestions','place_selection','source_coordinates','agent_goong_lookup','private_rest_key_not_in_bundle','no_page_errors']};
  fs.writeFileSync(path.join(out,'goong-preview-result.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify({passed:true,checks:result.checks,selected:{name:selected.name,longitude:selected.longitude,latitude:selected.latitude}}));
 }finally{await browser.close();}
})().catch(e=>{console.error(String(e));process.exit(1);});
