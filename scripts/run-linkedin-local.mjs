import {spawnSync} from 'node:child_process';
import {readFile,rename,writeFile,mkdir} from 'node:fs/promises';
import {linkedin} from '../src/linkedin.mjs';
import {localLinkedinReport} from '../src/linkedin-report.mjs';

const tests=process.argv.includes('--jakarta-only');
const statePath=tests?'.secrets/linkedin-smoke.json':'.secrets/linkedin-schedule.json';
const read=async path=>JSON.parse(await readFile(path,'utf8'));
const fourHours=4*3600_000;
const state=await read(statePath).catch(error=>{
 if(error.code==='ENOENT')return {};
 throw error;
});
const save=async()=>{
 await mkdir('.secrets',{recursive:true,mode:0o700});
 await writeFile(statePath+'.tmp',JSON.stringify(state),{mode:0o600});
 await rename(statePath+'.tmp',statePath);
};
const force=process.argv.includes('--force');
if(!force&&!state.pending&&Date.now()-(state.attemptedAt||0)<fourHours)process.exit(0);

const config=await read('config/search.json');
const marketList=tests?['Jakarta']:config.markets;
const role=tests?'QA Engineer':config.roles.map(title=>`"${title}"`).join(' OR ');
if(!state.pending){
 const online=spawnSync('gh',['api','rate_limit','--silent'],{timeout:10000,stdio:'ignore'});
 if(online.status!==0)process.exit(0);
 state.attemptedAt=Date.now();
 await save();
 const hoursSinceSuccess=state.lastSuccess?Math.ceil((Date.now()-state.lastSuccess)/3600_000):24;
 const lookbackSeconds=hoursSinceSuccess>24?7*86400:86400;
 const result=await linkedin(marketList.map(market=>({role,market})),{...config,lookbackSeconds});
 const report=localLinkedinReport({...result,scannedAt:new Date().toISOString()});
 const count=report.jobs.length;
 while(Buffer.byteLength(JSON.stringify(report))>57000)report.jobs.pop();
 if(report.jobs.length<count){
  report.status='limited';
  report.message+=` Sync kept ${report.jobs.length} of ${count} listings to fit GitHub's payload limit.`;
 }
 state.pending=report;
 await save();
}
const report=state.pending;
const payload=JSON.stringify({ref:'main',inputs:{linkedin_report:JSON.stringify(report)}});
const sent=spawnSync('gh',['api','--method','POST','repos/alif16syafri/job-scanner/actions/workflows/discovery.yml/dispatches','--input','-'],{
 input:payload,encoding:'utf8',timeout:20000
});
if(sent.status!==0)throw Error('GitHub did not accept the report. The Mac will retry the upload.');
if(report.status==='ok'||(report.status==='limited'&&report.jobs.length>0))state.lastSuccess=Date.parse(report.scannedAt);
delete state.pending;
await save();
console.log(`Uploaded ${report.jobs.length} public LinkedIn listings. ${report.message}`);
