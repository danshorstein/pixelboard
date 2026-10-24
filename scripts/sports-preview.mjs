import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const apiPort=process.env.SPORTS_API_PORT||'8125';
const webPort=process.env.SPORTS_WEB_PORT||'5177';
const children=[];
let stopping=false;
function stop(code=0){if(stopping)return;stopping=true;for(const child of children)child.kill('SIGTERM');process.exitCode=code;}
function start(command,args,env=process.env){
 const child=spawn(command,args,{cwd:root,env,stdio:'inherit'});children.push(child);
 child.on('error',error=>{console.error(error.message);stop(1);});
 child.on('exit',code=>{if(!stopping)stop(code||0);});
}
start(`${root}.venv/bin/python`,['-m','uvicorn','backend.sports_preview:app','--host','127.0.0.1','--port',apiPort,'--loop','asyncio']);
start(process.execPath,[`${root}node_modules/vite/bin/vite.js`,'--config','frontend/vite.config.ts','--host','127.0.0.1','--port',webPort,'--strictPort','--open','/sports'],{...process.env,SCOREBOARD_API_TARGET:`http://127.0.0.1:${apiPort}`});
console.log(`NBA/NHL browser preview: http://127.0.0.1:${webPort}/sports`);
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>stop());
