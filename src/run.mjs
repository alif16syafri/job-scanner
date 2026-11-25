import {readFile,writeFile,mkdir,rename} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {searchPlan,mergeJobs,canonical,triage,mergeSources} from './core.mjs';
import {employer,webSearch,sourceFor,safeUrl,get,parsePage} from './sources.mjs';
import {linkedin} from './linkedin.mjs';

const readJson=async p=>JSON.parse(await readFile(p,'utf8'));
const config=await readJson('config/search.json'),seeds=await readJson('config/sources.json');
const statePath=process.env.STATE_PATH||'data/state.json';
const old=existsSync(statePath)?await readJson(statePath):{version:1,jobs:{},sources:[],searchCursor:0,employerCursor:0,linkedinCursor:0};
if(old.version!==1)throw Error('Unsupported state version');
const now=new Date().toISOString(),health=[],incoming=[],newSources=[];
const plan=searchPlan(config,old.searchCursor),liPlan=searchPlan({...config,queriesPerRun:config.linkedinQueriesPerRun},old.linkedinCursor);
if(!process.env.BRAVE_SEARCH_API_KEY)health.push({source:'Broad web search',status:'limited',message:'Bing RSS is best effort and live checks returned weak coverage. Configure BRAVE_SEARCH_API_KEY for a dedicated search provider.'});
const sources=mergeSources(old.sources,seeds);
const selected=[...Array.from({length:Math.min(config.maxEmployerRefresh,sources.length)},(_,i)=>sources[((old.employerCursor||0)+i)%sources.length]),...seeds];
const detailQueue=new Map();
async function check(label,fn){try{const result=await fn();health.push({source:label,status:'ok',count:result.jobs?.length??result.length??0});return result;}catch(e){health.push({source:label,status:'error',message:String(e.message).slice(0,180)});return null;}}
for(const s of [...new Map(selected.map(s=>[canonical(s.url),s])).values()]){
 for(const url of s.jobUrls||[])detailQueue.set(url,{url,name:s.name});
 const result=await check(s.name,()=>employer(s));if(!result)continue;
 incoming.push(...result.jobs.map(j=>({...j,source:s.name})));
 for(const j of result.jobs)if(!j.description)detailQueue.set(j.url,{url:j.url,name:j.company});
 for(const url of result.links)detailQueue.set(url,{url,name:s.name});
}
for(const q of plan.queries){
 const jobs=await check(`Search: ${q.key}`,()=>webSearch(q.query));
 for(const j of (jobs||[]).slice(0,config.maxSearchResults)){
  try{safeUrl(j.url);incoming.push({...j,searchMarket:q.market});const source=sourceFor(j.url);if(source){newSources.push(source);detailQueue.set(j.url,{url:j.url,name:source.name});}}catch{}
 }
}
const li=await linkedin(liPlan.queries,config);incoming.push(...li.jobs);health.push({source:'LinkedIn',status:li.status,count:li.jobs.length,message:li.message});
for(const item of [...detailQueue.values()].slice(0,config.maxJobDetails)){
 if(/(^|\.)linkedin\.com$/.test(new URL(item.url).hostname))continue;
 const result=await check(`Detail: ${item.name}`,()=>employer({url:item.url,name:item.name,kind:'html'}));
 if(result)incoming.push(...result.jobs.map(j=>({...j,source:item.name})));
}
const jobs=mergeJobs(old.jobs,incoming,now);
for(const job of Object.values(jobs))job.triage=triage(job);
const allSources=mergeSources([...newSources.slice(0,config.maxNewEmployerPages),...sources],seeds);
const next={version:1,updatedAt:now,searchCursor:plan.nextCursor,linkedinCursor:liPlan.nextCursor,employerCursor:((old.employerCursor||0)+config.maxEmployerRefresh)%Math.max(sources.length,1),sources:allSources,jobs,health};
await mkdir('data',{recursive:true});await mkdir('reports',{recursive:true});
await writeFile(statePath+'.tmp',JSON.stringify(next,null,2)+'\n');await rename(statePath+'.tmp',statePath);
const esc=s=>String(s||'').replace(/[\r\n|]/g,' ').replace(/[<>]/g,'').replace(/\[/g,'(').replace(/\]/g,')');
const ranked=Object.values(jobs).filter(j=>j.triage.status!=='reject').sort((a,b)=>b.triage.score-a.triage.score);
const fresh=ranked.filter(j=>j.firstSeen===now);
const lines=['# Dita job discovery',`Run: ${now}`,`New candidates: ${fresh.length}. Total retained candidates: ${ranked.length}. Sources: ${allSources.length}.`,'','Discovery only. No applications are submitted. Scores are keyword heuristics, not verified qualifications.','', '## Source health',...health.map(h=>`- ${esc(h.source)}: **${h.status}**${h.count!==undefined?` (${h.count})`:''}${h.message?` — ${esc(h.message)}`:''}`),'','## New candidates','| Score | Job | Company / location | Checks |','|---|---|---|---|',...fresh.slice(0,100).map(j=>`| ${j.triage.score} | [${esc(j.title)}](${encodeURI(j.url).replace(/\)/g,'%29')}) | ${esc(j.company)} / ${esc(j.location)||'unverified'} | ${j.triage.flags.map(esc).join('; ')} |`),'','## Search coverage',...plan.queries.map(q=>`- Web: ${esc(q.key)}`),...liPlan.queries.map(q=>`- LinkedIn: ${esc(q.key)}`),'','Full history and rejection reasons: data/state.json. Results are first-seen records, not necessarily newly posted vacancies. Absence from a search does not prove closure.'];
const report=lines.join('\n')+'\n';await writeFile('reports/latest.md',report);
await writeFile('reports/latest.json',JSON.stringify({runAt:now,newJobs:fresh,rankedJobs:ranked,health},null,2)+'\n');
if(process.env.GITHUB_STEP_SUMMARY)await writeFile(process.env.GITHUB_STEP_SUMMARY,report,{flag:'a'});
console.log(`New candidates: ${fresh.length}; retained: ${ranked.length}; sources: ${allSources.length}; source issues: ${health.filter(h=>h.status!=='ok').length}`);
if(health.some(h=>h.status!=='ok'))process.exitCode=2;
