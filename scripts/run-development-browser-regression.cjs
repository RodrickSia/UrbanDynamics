const cp=require('child_process');
const fs=require('fs');
const path=require('path');
const root=path.resolve(__dirname,'..');
const out=path.join(root,'test-results','development-context');
fs.mkdirSync(out,{recursive:true});
fs.writeFileSync(path.join(out,'browser-regression.json'),JSON.stringify({status:'running'}));
const log=fs.openSync(path.join(out,'browser-regression.log'),'w');
const child=cp.spawn(process.execPath,['node_modules/@playwright/test/cli.js','test','--config=playwright.context.config.ts','--reporter=line'],
  {cwd:path.join(root,'frontend'),stdio:['ignore',log,log],windowsHide:true});
const deadline=setTimeout(()=>{
  if(process.platform==='win32') cp.spawnSync('taskkill',['/PID',String(child.pid),'/T','/F'],{stdio:'ignore',windowsHide:true});
  else child.kill('SIGTERM');
  fs.writeFileSync(path.join(out,'browser-regression.json'),JSON.stringify({passed:false,timeout:true}));
},180000);
child.on('close',code=>{
  clearTimeout(deadline);
  fs.closeSync(log);
  fs.writeFileSync(path.join(out,'browser-regression.json'),JSON.stringify({passed:code===0,code}));
});
