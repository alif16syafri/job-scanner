import {filterJobs} from './model.mjs';
const $=id=>document.getElementById(id);
let data=null;
const date=value=>value&&Number.isFinite(Date.parse(value))?new Intl.DateTimeFormat('en-GB',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Jakarta'}).format(new Date(value))+' WIB':'Not recorded';
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function link(url,title){const a=el('a',title);try{if(new URL(url).protocol!=='https:')return el('span',title);}catch{return el('span',title);}a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;}
function list(parent,title,items){if(!items?.length)return;parent.append(el('h4',title));const ul=el('ul');for(const item of items)ul.append(el('li',item));parent.append(ul);}
function readFilters(){const form=new FormData($('filters'));return {...Object.fromEntries(form),newOnly:$('newOnly').checked,updatedAt:data.updatedAt};}
function render(){
 if(!data)return;
 const jobs=filterJobs(data.jobs,readFilters());$('count').textContent=`${jobs.length} of ${data.jobs.length} saved jobs shown`;$('jobs').replaceChildren();$('empty').hidden=jobs.length!==0;
 if(!data.jobs.length){$('empty').querySelector('h3').textContent='No jobs in the saved scan yet';$('empty').querySelector('p').textContent='Review source health below, then check back after the next scheduled scan.';}
 for(const j of jobs){
  const card=el('article',undefined,'job'),top=el('div',undefined,'job-top'),heading=el('div');
  heading.append(el('p',j.company||'Employer unverified','company'));const h=el('h3');h.append(link(j.url,j.title));heading.append(h);
  const score=el('div',undefined,'score');score.append(el('strong',String(j.triage.score)),el('small','/ 100 match'));top.append(heading,score);card.append(top);
  card.append(el('p',[j.location||'Location unverified',j.employment||'Employment type unverified'].join(' · '),'meta'));
  const reasons=el('div',undefined,'reasons');for(const reason of j.triage.reasons)reasons.append(el('span',reason,'reason'));if(!j.triage.reasons.length)reasons.append(el('span','No verified keyword overlap','meta'));card.append(reasons);
  const status=el('p',undefined,'status-line');status.append(el('span',j.triage.status==='reject'?'Excluded by filters':j.triage.status==='match'?'Meets configured filters':'Needs review','status'));
  if(j.firstSeen===data.updatedAt)status.append(el('span','First seen this run'));
  status.append(el('span',`${j.triage.flags.length} checks to confirm`,'checks-count'));card.append(status);
  const details=el('details');details.append(el('summary','Match reasons and eligibility checks'));
  list(details,'Why it ranked here',j.triage.reasons);list(details,'Confirm before applying',j.triage.flags);list(details,'Why it was excluded',j.triage.rejections);
  details.append(el('p',`Sources: ${j.sources.join(', ')||'Not recorded'}`,'observed'),el('p',`First seen: ${date(j.firstSeen)}. Last seen: ${date(j.lastSeen)}.`,'observed'),el('p',`Posted: ${date(j.datePosted)}.`,'observed'));
  if(j.description){details.append(el('h4','Listing text'));details.append(el('p',j.description,'description'));}
  card.append(details);$('jobs').append(card);
 }
}
function options(id,values){const select=$(id);while(select.options.length>1)select.remove(1);for(const value of [...new Set(values)].filter(Boolean).sort())select.add(new Option(value,value));}
function health(){
 const issues=data.health.filter(h=>h.status!=='ok'),healthy=data.health.filter(h=>h.status==='ok');
 $('health-summary').textContent=`${issues.length} coverage issue${issues.length===1?'':'s'} · ${healthy.length} successful checks`;
 const rows=items=>{const box=el('div');for(const h of items){const row=el('div',undefined,'health-row'),name=el('div',h.source);if(h.message)name.append(el('small',h.message));row.append(name,el('span',({ok:'Checked',needs_login:'Needs login',limited:'Limited',error:'Error'})[h.status]||h.status,h.status==='ok'?'healthy':'problem'),el('span',h.count===null?'':`${h.count} found`,'quantity'));box.append(row);}return box;};
 $('health').replaceChildren();if(issues.length)$('health').append(rows(issues));else if(data.health.length)$('health').append(el('p','No source errors reported in the saved run.'));
 if(healthy.length){const details=el('details',undefined,'health-group');details.append(el('summary',`Successful checks (${healthy.length})`),rows(healthy));$('health').append(details);}
 if(!data.health.length)$('health').append(el('p','No source-health records available for this scan.'));
}
async function load(){
 $('error').hidden=true;$('jobs').setAttribute('aria-busy','true');$('retry').disabled=true;$('count').textContent='Loading saved jobs…';
 try{const response=await fetch('./data.json',{cache:'no-store'});if(!response.ok)throw Error('Data unavailable');const incoming=await response.json();if(!Array.isArray(incoming.jobs)||!Array.isArray(incoming.health))throw Error('Invalid scan data');data=incoming;
  $('updated').textContent=`Last scan: ${date(data.updatedAt)}`;
  const age=Date.now()-Date.parse(data.updatedAt);$('stale').hidden=Number.isFinite(age)&&age<=8*3600000;
  $('stale').textContent='This scan is more than 8 hours old, or its timestamp is missing. Check scan history before relying on freshness.';
  options('company',data.jobs.map(j=>j.company));options('location',data.jobs.map(j=>j.location));options('source',data.jobs.flatMap(j=>j.sources));health();render();
 }catch{data=null;$('error').hidden=false;$('jobs').replaceChildren();$('empty').hidden=true;$('count').textContent='Job data unavailable';$('updated').textContent='Latest scan could not be loaded';$('health-summary').textContent='Coverage data unavailable';}
 finally{$('jobs').setAttribute('aria-busy','false');$('retry').disabled=false;}
}
$('filters').addEventListener('submit',e=>e.preventDefault());$('filters').addEventListener('input',render);$('filters').addEventListener('change',render);
$('filters').addEventListener('reset',e=>{
 e.preventDefault();
 for(const control of $('filters').elements){
  if(control instanceof HTMLSelectElement)control.selectedIndex=0;
  else if(control instanceof HTMLInputElement){if(control.type==='checkbox')control.checked=control.defaultChecked;else control.value=control.defaultValue;}
 }
 render();
});
$('clear').addEventListener('click',()=>$('filters').reset());$('retry').addEventListener('click',load);
let theme='light';try{theme=localStorage.getItem('dita-theme')||'light';}catch{}
function setTheme(){document.documentElement.dataset.theme=theme;$('theme').textContent=theme==='dark'?'Light theme':'Dark theme';$('theme').setAttribute('aria-pressed',String(theme==='dark'));}
setTheme();$('theme').addEventListener('click',()=>{theme=theme==='dark'?'light':'dark';try{localStorage.setItem('dita-theme',theme);}catch{}setTheme();});
load();
