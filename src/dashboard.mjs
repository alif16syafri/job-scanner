import {readFile,mkdir,cp,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import * as cheerio from 'cheerio';
import {jobUrl} from './sources.mjs';

function text(value){let s=String(value||'');for(let i=0;i<2;i++)s=cheerio.load(s).text();return s.replace(/\s+/g,' ').trim();}
export function dashboardData(state){
 const jobs=Object.entries(state.jobs||{}).flatMap(([id,j])=>{
  let u;try{u=new URL(j.url);if(u.protocol!=='https:'||u.username||u.password||!jobUrl(j.url))return [];}catch{return [];}
  return [{id,title:text(j.title),company:text(j.company),location:text(j.location),url:u.href,description:text(j.description),employment:text(j.employment),datePosted:j.datePosted||null,firstSeen:j.firstSeen||null,lastSeen:j.lastSeen||null,sources:(j.sources||[j.source]).filter(Boolean).map(text),triage:{score:Number(j.triage?.score)||0,status:j.triage?.status||'review',reasons:(j.triage?.reasons||[]).map(text),flags:(j.triage?.flags||[]).map(text),rejections:(j.triage?.rejections||[]).map(text)}}];
 });
 return {updatedAt:state.updatedAt||null,jobs,health:(state.health||[]).map(h=>({source:text(h.source),status:text(h.status),count:h.count??null,message:text(h.message)}))};
}
export async function buildDashboard(statePath='data/state.json',directory='dist'){
 const state=JSON.parse(await readFile(statePath,'utf8'));
 await mkdir(directory,{recursive:true});await cp(new URL('../web/',import.meta.url),directory,{recursive:true});
 await writeFile(`${directory}/data.json`,JSON.stringify(dashboardData(state))+'\n');
 await writeFile(`${directory}/.nojekyll`,'');
 console.log('Built dashboard from saved public job data.');
}
if(process.argv[1]===fileURLToPath(import.meta.url))await buildDashboard();
