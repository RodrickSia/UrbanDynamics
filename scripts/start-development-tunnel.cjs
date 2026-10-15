const cp=require('child_process');
const child=cp.spawn('ssh',['-N','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes',
  '-o','ServerAliveInterval=30','-L','127.0.0.1:8192:127.0.0.1:51875','nguyenmv@192.168.20.156'],
  {detached:true,stdio:'ignore',windowsHide:true});
child.unref();
console.log('Development preview: http://127.0.0.1:8192 (requires access to server 156).');
