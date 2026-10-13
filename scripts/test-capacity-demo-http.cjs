const fs=require('fs'),path=require('path'),assert=require('assert');
const root=path.resolve(__dirname,'..'),out=path.join(root,'test-results','demo-capacity');
const base=process.env.PLANNING_DEMO_URL||'http://127.0.0.1:8007';
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const write=(name,value)=>fs.writeFileSync(path.join(out,name),JSON.stringify(value,null,2));
async function api(route,body){const r=await fetch(base+'/api/v1/planning'+route,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});const value=await r.json();if(!r.ok)throw Error(r.status+' '+JSON.stringify(value).slice(0,1000));return value;}
async function job(study,mode,name){const saved=await api('/studies',study);const task=await api('/studies/'+saved.id+'/runs',{mode,idempotency_key:crypto.randomUUID()});write(name+'-job.json',task);for(let i=0;i<1200;i++){const state=await api('/jobs/'+task.id);write(name+'-job.json',state);if(state.status==='succeeded'){const result=await api('/runs/'+state.result_id);write(name+'-result.json',result);return {job_id:task.id,result};}if(['failed','partial','cancelled'].includes(state.status))throw Error(JSON.stringify(state).slice(0,1500));await wait(1000);}throw Error('Job remains active; see saved job file, do not launch duplicate.');}
(async()=>{fs.mkdirSync(out,{recursive:true});write('http-execution.json',{status:'running'});
 const snapshots=(await api('/demo/system/snapshots')).snapshots;
 const snapshot=snapshots.find(s=>s.id==='0e62caa68cf5d4a1c9941cd82d59b8d4a09a453170dd09726c322d252bea2fda')||snapshots.at(-1);assert(snapshot,'Install a read-only system snapshot first');
 const features=(await api('/demo/system/snapshots/'+snapshot.id+'/parcels')).features;
 const ids=['1959486','1958467','1958799'].filter(id=>features.some(f=>String(f.id)===id));assert(ids.length===3,'Expected three frozen demo parcels');
 const prepared=(await api('/demo/system/prepare',{snapshot_id:snapshot.id,parcel_ids:ids,mode:'cumulative',background_mode:'synthetic_capacity_v1',sensitivity:true,sensitivity_engine:'screening',traffic_network_mode:'osm_snapshot',housing_units:20,residents:60,floors:4,floor_area_m2:1600,conditions:{traffic_hours:[18],seeds:[2026]}})).study;
 write('study.json',prepared);const preflight=await api('/studies/preflight',prepared);write('preflight.json',preflight);
 const screening=await job(prepared,'uncertainty','screening');
 assert(screening.result.uncertainty_analysis,'Sensitivity result missing');
 // Smaller declared OD and corridor for a bounded native smoke test; not a site calibration.
 const nativeStudy=(await api('/demo/system/prepare',{snapshot_id:snapshot.id,parcel_ids:[ids[0]],background_mode:'synthetic_capacity_v1',sensitivity:true,sensitivity_engine:'native',traffic_network_mode:'synthetic_corridor',traffic_peak_vehicles_hour:200,housing_units:20,residents:60,floors:4,floor_area_m2:1600,conditions:{traffic_hours:[18],seeds:[2026]}})).study;
 write('native-study.json',nativeStudy);const native=await job(nativeStudy,'uncertainty','native');
 const report={status:'passed',screening_url:base+'/simulation/planning?job='+screening.job_id,native_url:base+'/simulation/planning?job='+native.job_id,screening_job:screening.job_id,native_job:native.job_id,notes:'Screening real parcels/OSM with explicit fictional capacity; native single parcel, synthetic corridor, declared transferred OD 200/h and three seeds. Not calibrated traffic.'};
 write('http-execution.json',report);console.log(JSON.stringify(report));
})().catch(error=>{write('http-execution.json',{status:'failed',error:error.message});console.error(error.message);process.exitCode=1;});
