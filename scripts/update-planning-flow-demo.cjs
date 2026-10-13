// Rebuild first; preserve old containers and the existing runtime volume.
const cp=require('child_process'),path=require('path');
const repo=path.resolve(__dirname,'..');
const docker=args=>cp.execFileSync('docker',args,{encoding:'utf8',timeout:60000,stdio:['ignore','pipe','pipe']});
try{
 const check="import sqlite3,json; c=sqlite3.connect('/runtime/studies.sqlite'); n=c.execute(\"select count(*) from planning_jobs where status in ('queued','running')\").fetchone()[0]; print(n); assert n==0, 'Active jobs must finish before replacement'";
 docker(['run','--rm','--mount','type=volume,source=planning-program-runtime,target=/runtime','--entrypoint','python','planning-demo-backend:local','-c',check]);
 const snapshot=path.join(repo,'.runtime','planning-system','snapshots');
 const shared=['--mount','type=volume,source=planning-program-runtime,target=/runtime','--mount','type=bind,source='+snapshot+',target=/system-snapshots,readonly',
  '-e','PLANNING_SQLITE_PATH=/runtime/studies.sqlite','-e','SIMULATION_WORK_DIR=/runtime/solvers',
  '-e','PLANNING_BENCHMARK_MACHINE_ID=local-docker-worker','-e','PLANNING_SYSTEM_DEMO_ENABLED=1','-e','PLANNING_SYSTEM_SNAPSHOT_DIR=/system-snapshots','-e','PLANNING_SOLVER_TIMEOUT_SECONDS=600'];
 const backupSuffix='-before-flow-'+Date.now();
 for(const name of ['planning-program-api','planning-program-worker']){
  const state=JSON.parse(docker(['inspect',name]))[0].State;
  if(state.Running)docker(['stop',name]);
  docker(['rename',name,name+backupSuffix]);
 }
 docker(['run','-d','--name','planning-program-api','-p','127.0.0.1:8007:8000',...shared,'planning-demo-backend:local']);
 docker(['run','-d','--name','planning-program-worker',...shared,'planning-demo-backend:local','python','-m','app.services.simulation.planning.worker']);
 console.log('Updated API and worker on 8007; old containers and runtime volume preserved.');
}catch(e){console.error(String(e.message).slice(0,700));process.exitCode=1}
