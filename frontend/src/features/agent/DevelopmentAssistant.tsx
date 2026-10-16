import { useEffect, useRef, useState } from 'react';
import { GripVertical, Send, X, RefreshCw } from 'lucide-react';
import { PixelRobot } from './PixelRobot';
import { AssistantReply, AssistantText } from './AssistantReply';
import { useDraggableChat } from './useDraggableChat';
import { API_BASE_URL } from '../../services/api';
import type { ZoningWorkspace } from '../zoning/useZoning';
import type { SimulationJob, SimulationResult } from '../zoning/simulationTypes';
import { ComparisonTable } from '../zoning/DevelopmentSimulation';
import './developmentAssistant.css';

type Binding = {plan_id?: string; revision?: number; scenario_id?: string; parcel_id?: string; building_id?: string; dirty?: boolean; viewport?:number[];map_pois?:import('./mapPoi').MapPoiSnapshot;selected_place?:import('../map/types/map').PlaceDetails};
type Session = {session_id: string; messages: {role: string; content: string}[]; workspace?: Binding;
  workspace_changed?: boolean; map_actions?: {type: string; bbox?: number[]; layer_ids?: string[]}[];
  trace?: {tool: string; status: string; reason?: string}[];
  development_runs?: Record<string,{revision:number|null; plan_id:string|null; scenario_id:string|null; mode?:string;kind?:string}>;
  candidates?: import('geojson').FeatureCollection;
  query_features?: import('geojson').FeatureCollection|null;
  structured_queries?:{id:string;query:{layer:string};query_engine?:string;count_scope?:string;summary?:{conditions:string[];display_limit:number};matched_in_bounded_fetch:number;unknown_filter_rows:number;returned:number;source_truncated:boolean;result_limited:boolean;rows:Record<string,unknown>[];aggregates:{group:Record<string,unknown>;rows:number;metrics:{op:string;field:string|null;value:number|null;unknown_or_nonnumeric:number}[]}[];interpretation:string[];sources:{layer:string;alias?:string;relation?:string;radius_m?:number;metadata:Record<string,unknown>}[]}[];
  route_features?:import('geojson').FeatureCollection|null;
  route_result?:{source:string;vehicle:string;distance_m:number|null;duration_s:number|null;destination_name:string;interpretation:string};
  accessibility_results?:{id:string;source:string;vehicle:string;routing_status:string;shortlist:{parcels:number;facilities_per_category_per_parcel:number};limitations:string[];rows:{parcel_id:string;amenities:Record<string,{name:string|null;distance_m:number|null;duration_s:number|null;status:string}>}[]}[];
  analysis_area?:{title:string;source:string;bbox:number[];scope_summary?:{kind:string;area_m2:number;radius_m:number|null;source:string}};
  dataset_queries?:{layer:string;title:string;status:string;interpretation:string;records:{id:string|number;distance_m:number;quality?:string;properties:Record<string,unknown>}[]}[];
  amenity_search?:{status:string;sample_size:number;matching_in_sample:number;distance_method:string;amenity_source:{attribution:string;captured_at:string};results:{parcel_id:string;meets_all_proximity_requirements:boolean;amenities:Record<string,{name:string|null;distance_m:number|null;maximum_distance_m:number;meets_proximity:boolean}>}[]};
  area_reports?:{id:string;title:string;population:{year:number;estimated_people:number|null;coverage_percent:number|null};roads:{nearest_mapped_road_m?:number|null};buildings:{mapped_count?:number};capacity:Record<string,null>}[];
  assessments?:{id:string;ranking_status:string;method:string;excluded_from_all_scores:string[];unresolved:string[];rows:{parcel_id:string;score:number|null;qualification:string;missing_metrics:string[];priority_order:number|null}[]}[];
};

async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {method:body===undefined?'GET':'POST',
    headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(180000)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail==='string'?data.detail:`Request failed (${response.status})`);
  return data;
}

export function DevelopmentAssistant({workspace:w,onClose,onBusy,onMapAction,viewport,mapPois,onCandidates,selectedPlace}: {
  workspace: ZoningWorkspace; onClose:()=>void; onBusy:(busy:boolean)=>void;
  viewport?:number[];mapPois?:import('./mapPoi').MapPoiSnapshot;onCandidates?:(features:import('geojson').FeatureCollection)=>void;
  selectedPlace?:import('../map/types/map').PlaceDetails|null;
  onMapAction:(action:{type:string; bbox?:number[]; layer_ids?:string[]})=>string[];
}) {
  const [session,setSession]=useState<Session|null>(null), [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false), [error,setError]=useState(''), [mapNotes,setMapNotes]=useState<string[]>([]);
  const [pendingMessage,setPendingMessage]=useState<{content:string;failed:boolean}|null>(null);
  const [allowNative,setAllowNative]=useState(false);
  const [config,setConfig]=useState<{enabled:boolean;model_configured:boolean;model:string;requires_token:boolean}>();
  const [jobs,setJobs]=useState<Record<string,SimulationJob>>({}), [jobId,setJobId]=useState('');
  const [result,setResult]=useState<SimulationResult>();
  const [pollEpoch,setPollEpoch]=useState(0);
  const [replyStart, setReplyStart] = useState(Infinity);
  const chat = useDraggableChat();
  const draft = useRef<{message:string;id:string}|null>(null);
  const end=useRef<HTMLDivElement>(null);
  const focusCandidate = (feature: import('geojson').Feature) => {
    const coordinates: number[][] = [];
    const collect = (value: unknown): void => {
      if (!Array.isArray(value)) return;
      if (typeof value[0] === 'number' && typeof value[1] === 'number') {
        if (Number.isFinite(value[0]) && Number.isFinite(value[1])) coordinates.push([value[0], value[1]]);
      } else value.forEach(collect);
    };
    const geometry = (value: import('geojson').Geometry | null): void => {
      if (!value) return;
      if (value.type === 'GeometryCollection') value.geometries.forEach(geometry);
      else collect(value.coordinates);
    };
    geometry(feature.geometry);
    if (!coordinates.length) { setError('This candidate has no mapped location.'); return; }
    const bbox = coordinates.reduce(([west,south,east,north],[x,y]) =>
      [Math.min(west,x),Math.min(south,y),Math.max(east,x),Math.max(north,y)],
      [Infinity,Infinity,-Infinity,-Infinity]);
    setError('');
    onMapAction({type:'focus',bbox});
  };
  const binding:Binding={plan_id:w.plan?.id,revision:w.plan?.revision,scenario_id:w.scenario?.id,
    parcel_id:w.development.parcelId||undefined,building_id:w.development.selectedBuilding||undefined,dirty:w.development.dirty,viewport,map_pois:mapPois,selected_place:selectedPlace??undefined};
  const selectedIds=Object.keys(session?.development_runs??{});
  const idsKey=selectedIds.join(',');
  useEffect(()=>{void api<typeof config>('/api/v1/agent/config').then(setConfig).catch(e=>setError(String(e)));
    const id=localStorage.getItem('development-assistant-session');
    if(id)void api<Session>(`/api/v1/agent/sessions/${encodeURIComponent(id)}`).then(setSession).catch(()=>localStorage.removeItem('development-assistant-session'));
  },[]);
  useEffect(()=>{end.current?.scrollIntoView({block:'nearest'});},[session?.messages.length,busy]);
  useEffect(()=>{const base=session?.query_features??session?.candidates??{type:'FeatureCollection' as const,features:[]};onCandidates?.({type:'FeatureCollection',features:[...base.features,...(session?.route_features?.features??[])]});},[session?.candidates,session?.query_features,session?.route_features]);
  useEffect(()=>{if(!w.plan&&session?.analysis_area?.bbox)onMapAction({type:'focus',bbox:session.analysis_area.bbox});},[session?.session_id]);
  useEffect(()=>{
    let alive=true,timer:ReturnType<typeof setTimeout>|undefined;
    const poll=async()=>{
      const statuses=await Promise.all(selectedIds.map(async id=>{try{return await api<SimulationJob>(`/api/v1/planning/jobs/${id}`);}catch{return null;}}));
      if(!alive)return;
      setJobs(Object.fromEntries(statuses.filter((j):j is SimulationJob=>j!==null).map(j=>[j.id,j])));
      if(statuses.some(j=>j&&['queued','running'].includes(j.status)))timer=setTimeout(poll,2500);
    };
    if(selectedIds.length)void poll();
    return()=>{alive=false;clearTimeout(timer);};
  },[idsKey,pollEpoch]);
  const currentJob=jobs[jobId];
  useEffect(()=>{
    setResult(undefined);
    if(currentJob?.status!=='succeeded'||!currentJob.result_id)return;
    let alive=true;
    void api<SimulationResult>(`/api/v1/planning/runs/${currentJob.result_id}`).then(r=>{if(alive)setResult(r);}).catch(e=>{if(alive)setError(String(e));});
    return()=>{alive=false;};
  },[jobId,currentJob?.status,currentJob?.result_id]);
  const accept=async(next:Session)=>{
    setReplyStart(session?.messages.length ?? 0);
    setPendingMessage(null);
    setSession(next);localStorage.setItem('development-assistant-session',next.session_id);
    if(next.workspace_changed&&next.workspace)await w.acceptAssistant(next.workspace);
    const actions=next.map_actions??[];
    const layerIds=[...new Set(actions.flatMap(a=>a.type==='layers'?a.layer_ids??[]:[]))];
    const notes=layerIds.length?onMapAction({type:'layers',layer_ids:layerIds}):[];
    const focus=actions.filter(a=>a.type==='focus'&&a.bbox).at(-1);
    if(focus)notes.push(...onMapAction(focus));
    setMapNotes(notes);
    const ids=Object.keys(next.development_runs??{});if(ids.length)setJobId(ids.at(-1)!);
  };
  const send=async(text=message)=>{
    if(busy||!text.trim())return;
    setBusy(true);onBusy(true);setError('');
    setPendingMessage({content:text,failed:false});setMessage('');
    if(draft.current?.message!==text)draft.current={message:text,id:crypto.randomUUID()};
    try{
      let active=session;
      if(!active){active=await api<Session>('/api/v1/agent/sessions',{});setSession(active);localStorage.setItem('development-assistant-session',active.session_id);}
      const next=await api<Session>('/api/v1/agent/chat',{session_id:active.session_id,message:text,
        request_id:draft.current.id,workspace:binding,selected_parcel_ids:binding.parcel_id?[binding.parcel_id]:[],allow_native:allowNative});
      await accept(next);setMessage('');draft.current=null;
    }catch(e){setPendingMessage({content:text,failed:true});setMessage(text);setError(e instanceof Error?e.message:'Assistant unavailable. Saved plans and jobs remain available.');}
    finally{setBusy(false);onBusy(false);}
  };
  const refresh=async()=>{if(session)try{setSession(await api<Session>(`/api/v1/agent/sessions/${session.session_id}`));setPollEpoch(n=>n+1);}catch(e){setError(String(e));}};
  return <aside ref={chat.panel} className="development-assistant solid-panel zoning-ui" aria-label="Planning assistant">
    <header><button type="button" className="assistant-drag-handle" aria-label="Move chat" title="Drag to move · Arrow keys to move · Home to reset" {...chat.handle}>
      <GripVertical size={17}/><span>Planning assistant</span></button>
      <button aria-label="Close assistant" disabled={busy} onClick={onClose}><X size={17}/></button></header>
    {(w.plan || session?.analysis_area || binding.parcel_id || binding.dirty) && <div className="assistant-context">
      {w.plan && <><strong>{w.plan.name}</strong><span>{w.scenario?.name} · revision {w.plan.revision}</span></>}
      {session?.analysis_area&&<span>Analysis area: {session.analysis_area.title}</span>}
      {session?.analysis_area?.source.includes('Nominatim')&&<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">Place lookup © OpenStreetMap contributors · Nominatim</a>}
      {binding.parcel_id&&<span>Site {binding.parcel_id}{binding.building_id?' · building selected':''}</span>}
      {binding.dirty&&<p>Save or discard your unfinished proposal before AI edits or runs.</p>}
    </div>}
    <div className="assistant-scroll">
      {!session?.messages.length&&!pendingMessage&&<div className="assistant-welcome"><h3>Explore, compare and plan</h3>
        <p>Ask about an area, find sites, compare tradeoffs, review a plan or simulate a building. You can start from the visible map. Missing data stays unknown.</p>
        <div className="assistant-prompts">{['Analyze the visible map: population, buildings, roads, flooding and available sources.','Find 3 sites between 2,000 and 10,000 m² in the visible area. Explain what is still unknown.','Explain the current plan and its data gaps.','Read the latest completed simulation and explain the results.'].map(text=><button disabled={busy||!config?.model_configured} key={text} onClick={()=>void send(text)}>{text}</button>)}</div></div>}
      <div aria-live="polite" className="assistant-messages">{session?.messages.map((m,i)=>m.role === 'assistant'
        ? <AssistantReply key={`${session.session_id}-${i}`} text={m.content} animate={i >= replyStart}/>
        : <article key={`${session.session_id}-${i}`} data-role={m.role}><strong>You</strong><AssistantText text={m.content}/></article>)}
        {pendingMessage&&!(pendingMessage.failed&&session?.messages.at(-1)?.role==='user'&&session.messages.at(-1)?.content===pendingMessage.content)&&<article data-role="user" data-pending="true"><strong>You</strong><AssistantText text={pendingMessage.content}/>{pendingMessage.failed&&<small>No response received. Retry this message or refresh.</small>}</article>}
        {busy&&pendingMessage&&!pendingMessage.failed&&<div role="status" className="assistant-thinking"><PixelRobot state="thinking"/><span>Thinking…</span></div>}
        <div ref={end}/>
      </div>
      {!!session?.trace?.length&&<details><summary>Actions taken</summary><ul>{session.trace.map((t,i)=><li key={i}>{t.tool.replaceAll('_',' ')} · {t.status}{t.reason?` · ${t.reason}`:''}</li>)}</ul></details>}
      {mapNotes.map((note,i)=><p key={i} role="status">{note}</p>)}
      {!!session?.area_reports?.length&&<details><summary>Area evidence</summary>{session.area_reports.map(a=><section key={a.id}><h4>{a.title}</h4><p>WorldPop {a.population.year}: {a.population.estimated_people?.toLocaleString()??'Unknown'} modelled people · coverage {a.population.coverage_percent?.toFixed(1)??'Unknown'}%.</p><p>Mapped buildings: {a.buildings.mapped_count??'Unknown'} · nearest mapped road: {a.roads.nearest_mapped_road_m?.toFixed(0)??'Unknown'} m. Utility capacity remains unknown.</p></section>)}</details>}
      {!!session?.structured_queries?.length&&<details open><summary>Filtered dataset results</summary>{session.structured_queries.slice(-1).map(q=><section key={q.id}>
        <h4>{q.query.layer} · {q.matched_in_bounded_fetch.toLocaleString()} matches {q.query_engine==='postgis'?'in scoped source records':'in fetched records'}</h4>
        {q.query_engine==='postgis'&&<small>Database filters applied before display limit. {q.count_scope}</small>}
        {q.summary&&<ul>{q.summary.conditions.map((condition,i)=><li key={i}>{condition}</li>)}</ul>}
        <p>{q.returned} shown on map · {q.unknown_filter_rows} excluded because filter values are unknown{q.source_truncated?' · Source fetch limit reached':''}{q.result_limited?' · Display limit reached':''}</p>
        <small>Query {q.id}</small>
        <div style={{overflowX:'auto',maxHeight:320}}><table><thead><tr>{Object.keys(q.rows[0]??{}).map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{q.rows.map((r,i)=><tr key={i}>{Object.keys(q.rows[0]??{}).map(k=><td key={k}>{r[k]==null?'Unknown':typeof r[k]==='object'?JSON.stringify(r[k]):String(r[k])}</td>)}</tr>)}</tbody></table></div>
        {q.aggregates.map((a,i)=><p key={i}>{Object.keys(a.group).length?JSON.stringify(a.group):'All matched records'}: {a.metrics.map(m=>`${m.op}(${m.field??'*'}) = ${m.value??'Unknown'}${m.unknown_or_nonnumeric?` (${m.unknown_or_nonnumeric} unknown/non-numeric)`:''}`).join(' · ')}</p>)}
        <details><summary>Filters and source evidence</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify({query:q.query,sources:q.sources},null,2)}</pre></details>
        {q.interpretation.map(t=><small key={t} style={{display:'block'}}>{t}</small>)}
      </section>)}</details>}
      {!!session?.dataset_queries?.length&&<details open><summary>Dataset evidence</summary>{session.dataset_queries.map((q,i)=><section key={`${q.layer}-${i}`}><h4>{q.title}</h4><p>{q.records.length} source records · {q.status.replaceAll('_',' ')}</p>{q.records.slice(0,5).map(r=><p key={r.id}><strong>{String(r.properties.road??r.id)}</strong> · {r.distance_m.toFixed(0)} m from query area{r.properties.residential_vnd_m2!=null&&<> · residential reference: {Number(r.properties.residential_vnd_m2).toLocaleString()} VND/m²</>}{r.properties.effective_from!=null&&<> · effective {String(r.properties.effective_from)}</>}</p>)}<small>{q.interpretation}</small></section>)}</details>}
      {session?.amenity_search&&<details open><summary>Amenities near candidate sites</summary><p>{session.amenity_search.matching_in_sample} matching sites in the evaluated sample/shortlist (parcel sample: {session.amenity_search.sample_size}). {session.amenity_search.distance_method}</p>{session.amenity_search.results.map(r=><section key={r.parcel_id}><h4>Parcel {r.parcel_id} · {r.meets_all_proximity_requirements?'Meets proximity filters':'Partial match'}</h4>{Object.entries(r.amenities).map(([category,a])=><p key={category}><strong>{category}</strong>: {a.name??'No mapped match'} · {a.distance_m==null?'Unknown distance':`${a.distance_m.toFixed(0)} m`} (limit {a.maximum_distance_m} m) · {a.meets_proximity?'Pass':'Not met'}</p>)}</section>)}<small>{session.amenity_search.amenity_source.attribution} · captured {session.amenity_search.amenity_source.captured_at}</small></details>}
      {!session?.query_features&&!!session?.candidates?.features.length&&<details open><summary>Candidate sites · vacancy unverified</summary>{session.candidates.features.map(f=><button type="button" key={f.id} title="Show this parcel on the map" aria-label={`Show parcel ${f.id} on map`} onClick={()=>focusCandidate(f)}>Parcel {f.id} · {Math.round(Number(f.properties?.area_m2??0)).toLocaleString()} m²</button>)}</details>}
      {!!session?.accessibility_results?.length&&<details open><summary>Travel access · Goong routes</summary>{session.accessibility_results.slice(-1).map(result=><section key={result.id}><p>{result.source} · {result.vehicle} · {result.routing_status.replaceAll('_',' ')}</p><small>{result.shortlist.parcels} shortlisted parcels; up to {result.shortlist.facilities_per_category_per_parcel} mapped facilities per category and parcel.</small>{result.rows.map(row=><section key={row.parcel_id}><h4>Parcel {row.parcel_id}</h4>{Object.entries(row.amenities).map(([category,amenity])=><div key={category}><p>{category}: {amenity.name??'Unknown mapped destination'} · {amenity.distance_m==null?'Unknown distance':`${Math.round(amenity.distance_m)} m by route`} · {amenity.duration_s==null?'Unknown time':`${(amenity.duration_s/60).toFixed(1)} min`}</p>{amenity.status==='available'&&<button disabled={busy} onClick={()=>void(async()=>{setBusy(true);try{await accept(await api<Session>(`/api/v1/agent/sessions/${session.session_id}/tools/route_show`,{arguments:{accessibility_id:result.id,parcel_id:row.parcel_id,category},workspace:binding}));}catch(e){setError(String(e));}finally{setBusy(false);}})()}>Show route to {category}</button>}</div>)}</section>)}{result.limitations.map(text=><small key={text} style={{display:'block'}}>{text}</small>)}</section>)}</details>}
      {session?.route_result&&<p>Displayed route to {session.route_result.destination_name} · {session.route_result.vehicle} · {session.route_result.distance_m==null?'Unknown distance':`${Math.round(session.route_result.distance_m)} m`} · {session.route_result.duration_s==null?'Unknown time':`${(session.route_result.duration_s/60).toFixed(1)} min`}. {session.route_result.interpretation}</p>}
      {session?.analysis_area?.scope_summary&&<details><summary>Analysis boundary</summary><p>{session.analysis_area.scope_summary.kind.replaceAll('_',' ')} · {(session.analysis_area.scope_summary.area_m2/1000000).toFixed(2)} km²{session.analysis_area.scope_summary.radius_m!=null?` · radius ${session.analysis_area.scope_summary.radius_m} m`:''}</p><small>{session.analysis_area.scope_summary.source}</small></details>}
      {!!session?.assessments?.length&&<details open className="assistant-assessments"><summary>Site comparison · declared criteria</summary>{session.assessments.map(a=><section key={a.id}><p>{a.ranking_status.replaceAll('_',' ')}</p><table><thead><tr><th>Parcel / status</th><th>Priority score</th><th>Data gaps</th></tr></thead><tbody>{a.rows.map(row=><tr key={row.parcel_id}><td>{row.parcel_id}<small>{row.qualification.replaceAll('_',' ')}</small></td><td>{row.priority_order==null?'Not ranked':row.score?.toFixed(1)}</td><td>{row.missing_metrics.join(', ')||'See unresolved requirements'}</td></tr>)}</tbody></table><p>{a.method}</p><p>Unresolved: {a.unresolved.join('; ')}.</p></section>)}</details>}
      {!!selectedIds.length&&<section className="assistant-results"><h3>Saved simulation runs</h3>
        <label>Run<select aria-label="Assistant simulation run" value={jobId} onChange={e=>setJobId(e.target.value)}><option value="">Choose a run</option>{selectedIds.map(id=><option key={id} value={id}>{id.slice(0,8)} · {jobs[id]?.status??'Loading'} · {session?.development_runs?.[id].kind==='urban_comparison'?'Site study':`r${session?.development_runs?.[id].revision}`}</option>)}</select></label>
        {jobId&&<p role="status">{currentJob?.status??'Loading'} · {jobId}</p>}
        {session?.development_runs?.[jobId]&&session.development_runs[jobId].kind!=='urban_comparison'&&(session.development_runs[jobId].plan_id!==w.plan?.id||session.development_runs[jobId].scenario_id!==w.scenario?.id)&&<p className="assistant-warning">This saved run belongs to a different plan or scenario from the current map selection.</p>}
        {session?.development_runs?.[jobId]?.plan_id===w.plan?.id&&session?.development_runs?.[jobId]?.revision!==w.plan?.revision&&<p className="assistant-warning">Historical result: the plan has changed. Run again to evaluate current inputs.</p>}
        {result&&<><p>Saved {result.mode==='native'?'SUMO + SWMM':'Quick estimate'} result. Inputs are frozen; unknown baseline does not mean zero.</p>
          {result.options.map(o=><section key={o.id}><h4>{o.id}</h4><ComparisonTable rows={[...o.comparison,...(o.drainage_comparison??[])].map(r=>({...r,after:r.after??o.state.metrics[r.metric]??null}))}/>
            {!!o.traffic_comparison?.length&&<ComparisonTable traffic rows={o.traffic_comparison}/>}</section>)}
          <a target="_blank" rel="noreferrer" href={`${API_BASE_URL}/api/v1/planning/runs/${result.id}`}>Full result and sources</a></>}
      </section>}
      {error&&<p role="alert" className="assistant-warning">{error}</p>}
    </div>
    <form onSubmit={e=>{e.preventDefault();void send();}} className="assistant-composer">
      <label className="assistant-native"><input type="checkbox" checked={allowNative} disabled={busy} onChange={e=>setAllowNative(e.target.checked)}/>Allow detailed SUMO/SWMM runs</label>
      {config&&!config.model_configured&&<p>Model is not configured on this backend.</p>}
      {config?.requires_token&&<p>This preview needs an access token configured by the administrator.</p>}
      <label className="sr-only" htmlFor="assistant-message">Message to planning assistant</label>
      <textarea id="assistant-message" value={message} disabled={busy} maxLength={4000} rows={3} onChange={e=>setMessage(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();if(!busy&&message.trim()&&config?.enabled&&config.model_configured&&!config.requires_token)e.currentTarget.form?.requestSubmit();}}} placeholder="Ask about an area, find sites, compare options or simulate impacts…"/>
      <div><button type="button" disabled={busy||!session} onClick={()=>void refresh()} title="Refresh saved session"><RefreshCw size={15}/>Refresh</button>
        <button type="button" disabled={busy} onClick={()=>{setSession(null);setPendingMessage(null);setJobId('');setJobs({});setResult(undefined);setError('');draft.current=null;localStorage.removeItem('development-assistant-session');}}>New chat</button>
        <button className="zoning-primary" type="submit" disabled={busy||!message.trim()||!config?.enabled||!config.model_configured||config.requires_token}><Send size={15}/>Send</button></div>
    </form>
  </aside>;
}
