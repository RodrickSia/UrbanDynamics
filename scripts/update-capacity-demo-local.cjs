// Patch existing local containers only; preserve their database, snapshots and old jobs.
const cp=require('child_process'),path=require('path');
const root=path.resolve(__dirname,'..');
const docker=args=>cp.execFileSync('docker',args,{encoding:'utf8',timeout:60000,stdio:['ignore','pipe','pipe']});
const check="import sqlite3; c=sqlite3.connect('/runtime/studies.sqlite'); n=c.execute(\"select count(*) from planning_jobs where status in ('queued','running')\").fetchone()[0]; print(n); assert n==0, 'Wait for active jobs before updating'";
try {
  docker(['run','--rm','--mount','type=volume,source=planning-program-runtime,target=/runtime','--entrypoint','python','planning-demo-backend:local','-c',check]);
  const files=['services/simulation/planning/demo_capacity.py','services/simulation/planning/system_demo.py','services/simulation/planning/provenance.py','static/planning.html','static/planning.js'];
  for(const name of ['planning-program-api','planning-program-worker']) {
    const state=JSON.parse(docker(['inspect',name]))[0].State;
    if(state.Running)docker(['stop',name]);
    for(const file of files)docker(['cp',path.join(root,'backend','app',file),name+':/app/app/'+file]);
    docker(['start',name]);
  }
  console.log('Updated local 8007 API and worker. Existing jobs and read-only snapshots retained.');
}catch(error){console.error(error.message.slice(0,1000));process.exitCode=1;}
