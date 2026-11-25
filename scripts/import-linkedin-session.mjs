import {chromium} from 'playwright';
import {randomUUID} from 'node:crypto';
import {mkdir,readFile,rename,rm,writeFile} from 'node:fs/promises';
import {homedir} from 'node:os';
import {dirname,join,resolve} from 'node:path';

const portFile=join(homedir(),'Library/Application Support/Google/Chrome/DevToolsActivePort');
const output=resolve(process.env.LINKEDIN_STATE_PATH||'.secrets/linkedin.json');
const partial=join(dirname(output),`.linkedin-${randomUUID()}.tmp`);

async function importSession(){
 const portInfo=await readFile(portFile,'utf8').catch(()=>null);
 if(!portInfo)throw Error('Enable remote debugging in Chrome before importing the session.');
 const [port,endpoint]=portInfo.trim().split(/\r?\n/);
 if(!/^\d+$/.test(port)||!/^\/devtools\/browser\/[a-z\d-]+$/i.test(endpoint)){
  throw Error('Chrome did not provide an active local debugging connection.');
 }
 const browser=await chromium.connectOverCDP(`ws://127.0.0.1:${port}${endpoint}`,{
  isLocal:true,noDefaults:true,timeout:90000
 }).catch(()=>{throw Error('Chrome did not allow the local debugging connection.');});
 try{
  const tabs=browser.contexts().flatMap(context=>context.pages()).filter(page=>{
   const url=new URL(page.url());
   return url.hostname==='www.linkedin.com'&&(url.pathname==='/jobs'||url.pathname.startsWith('/jobs/'));
  });
  if(tabs.length!==1)throw Error('A single LinkedIn Jobs tab must be visible to Chrome debugging to identify the right account.');
  const [tab]=tabs;
  const cookies=(await tab.context().cookies('https://www.linkedin.com/'))
   .filter(cookie=>/(^|\.)linkedin\.com$/i.test(cookie.domain));
  if(!cookies.some(cookie=>cookie.name==='li_at'&&cookie.value))throw Error('The selected LinkedIn Jobs tab does not have an active login.');
  await mkdir(dirname(output),{recursive:true,mode:0o700});
  await writeFile(partial,JSON.stringify({cookies,origins:[]}),{mode:0o600,flag:'wx'});
  await rename(partial,output);
  console.log('Saved the LinkedIn-only session locally for the headless scanner.');
 }finally{
  await rm(partial,{force:true});
  await browser.close();
 }
}

try{
 await importSession();
}catch(error){
 console.error(error.message);
 process.exitCode=1;
}
