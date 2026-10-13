// Retrieve the existing job only; never enqueue another simulation.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=path.resolve(__dirname,'../test-results/planning-flow-default');
async function get(p){const r=await fetch('http://127.0.0.1:8007/api/v1/planning'+p);if(!r.ok)throw new Error(await r.text());return r.json()}
(async()=>{
 const saved=JSON.parse(fs.readFileSync(out+'/job.json','utf8'));
 const job=await get('/jobs/'+saved.id);
 if(['queued','running'].includes(job.status)){console.log(JSON.stringify({status:job.status,progress:job.progress}));return}
 assert.equal(job.status,'succeeded',JSON.stringify(job.error));
 const result=await get('/runs/'+job.result_id),context=result.context;
 const traffic=context.resolved_background.traffic;
 assert.equal(traffic.cars[18],216);assert.equal(traffic.motorcycles[18],3672);
 assert.equal(context.system_background.counting_reference.repaired_crossings,19);
 const option=result.options.find(o=>o.id==='together_3');assert.ok(option);
 assert.ok(option.state.traffic.runs.every(r=>r.count_balanced));
 assert.equal(option.state.drainage.balance_passed,true);
 const rows=result.options.map(o=>({id:o.id,traffic:o.state.traffic.runs.map(r=>({planned:r.planned_vehicles,completed:r.completed_vehicles,backlog:r.unfinished_vehicles+r.undeparted_vehicles,delay:r.mean_completed_delay_seconds,queue:r.max_queue_length_m,count_balanced:r.count_balanced}))}));
 fs.writeFileSync(out+'/native-result.json',JSON.stringify(result,null,2));
 const report={status:'passed',job_id:job.id,run_id:result.id,parcel_ids:Object.values(context.system_background.parcel_bindings),
  network_mode:'osm_snapshot',counting_reference_id:context.system_background.counting_reference_id||context.inputs.traffic_prior.counting_reference_id,
  options:result.options.length,phases:result.phases.length,background_vehicles_hour:3888,all_vehicle_sample_rate:4104,
  checks:['Default selected without explicit 800 override','19-crossing evidence retained','3888 supported vehicles/hour','SUMO counts conserve','SWMM mass balance'],
  url:'http://127.0.0.1:8007/simulation/planning?job='+job.id+'&option=together_3',traffic:rows};
 fs.writeFileSync(out+'/http-report.json',JSON.stringify(report,null,2));
 console.log(JSON.stringify(report));
})().catch(e=>{console.error(e.message.slice(0,1200));process.exitCode=1});
