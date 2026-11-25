import {filterJobs} from './model.mjs';
const $=id=>document.getElementById(id);
let data=null;
let selectedId=null;
let mobileDetail=false;
const narrow=matchMedia('(max-width: 720px)');
const date=value=>value&&Number.isFinite(Date.parse(value))?new Intl.DateTimeFormat('en-GB',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Jakarta'}).format(new Date(value))+' WIB':'Not recorded';
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function link(url,title){const a=el('a',title);try{if(new URL(url).protocol!=='https:')return el('span',title);}catch{return el('span',title);}a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;}
function list(parent,title,items){if(!items?.length)return;parent.append(el('h4',title));const ul=el('ul');for(const item of items)ul.append(el('li',item));parent.append(ul);}
function readFilters(){const form=new FormData($('filters'));return {...Object.fromEntries(form),newOnly:$('newOnly').checked,updatedAt:data.updatedAt};}
function render(){
 if(!data)return;
 const jobs=filterJobs(data.jobs,readFilters());$('count').textContent=`${jobs.length} of ${data.jobs.length} saved jobs shown`;$('jobs').replaceChildren();$('empty').hidden=jobs.length!==0;
 if(!data.jobs.length){$('empty').querySelector('h3').textContent='No jobs in the saved scan yet';$('empty').querySelector('p').textContent='Review source health below, then check back after the next scheduled scan.';}
 if(!jobs.some(job=>job.id===selectedId)){
  selectedId=jobs[0]?.id??null;
  mobileDetail=false;
 }
 for(const job of jobs){
  const row=el('button',undefined,'job-row');
  row.type='button';
  row.dataset.jobId=job.id;
  row.setAttribute('aria-pressed',String(job.id===selectedId));
  row.setAttribute('aria-controls','job-detail');
  const label=el('span',undefined,'row-label');
  label.append(el('span',job.company||'Employer unverified','company'),el('strong',job.title),el('span',job.location||'Location unverified','meta'));
  const metrics=el('span',undefined,'row-metrics');
  const seen=Number.isFinite(Date.parse(job.firstSeen))?new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',timeZone:'Asia/Jakarta'}).format(new Date(job.firstSeen)):'Date unknown';
  metrics.append(el('strong',String(job.triage.score),'row-score'),el('span',job.firstSeen&&job.firstSeen===data.updatedAt?'New':seen));
  row.append(label,metrics);
  row.addEventListener('click',()=>{
   selectedId=job.id;
   mobileDetail=narrow.matches;
   showJob(job);
   if(mobileDetail)$('back').focus();
  });
  $('jobs').append(row);
 }
 showJob(jobs.find(job=>job.id===selectedId));
}
function showJob(j){
 const panel=$('job-detail');
 panel.replaceChildren();
 panel.hidden=!j;
 $('split').classList.toggle('show-detail',mobileDetail);
 for(const row of $('jobs').children)row.setAttribute('aria-pressed',String(row.dataset.jobId===selectedId));
 if(!j)return;
 const back=el('button','Back to jobs','back');
 back.id='back';
 back.type='button';
 back.addEventListener('click',()=>{
  mobileDetail=false;
  $('split').classList.remove('show-detail');
  [...$('jobs').children].find(row=>row.dataset.jobId===selectedId)?.focus();
 });
 panel.append(back);
 const card=el('article',undefined,'job'),top=el('div',undefined,'job-top'),heading=el('div');
  heading.append(el('p',j.company||'Employer unverified','company'),el('h3',j.title));
  const score=el('div',undefined,'score');score.append(el('strong',String(j.triage.score)),el('small','/ 100 match'));top.append(heading,score);card.append(top);
  card.append(el('p',[j.location||'Location unverified',j.employment||'Employment type unverified'].join(' · '),'meta'));
  const outbound=link(j.url,'View original listing');outbound.className='listing-link';card.append(outbound);
  const status=el('p',undefined,'status-line');status.append(el('span',j.triage.status==='reject'?'Excluded by filters':j.triage.status==='match'?'Meets configured filters':'Needs review','status'));
  if(j.firstSeen===data.updatedAt)status.append(el('span','First seen this run'));
  status.append(el('span',`${j.triage.flags.length} checks to confirm`,'checks-count'));card.append(status);
  const details=el('div',undefined,'reason-panel');
  list(details,'Why it ranked here',j.triage.reasons);list(details,'Confirm before applying',j.triage.flags);list(details,'Why it was excluded',j.triage.rejections);
  details.append(el('p',`Sources: ${j.sources.join(', ')||'Not recorded'}`,'observed'),el('p',`First seen: ${date(j.firstSeen)}. Last seen: ${date(j.lastSeen)}.`,'observed'),el('p',`Posted: ${date(j.datePosted)}.`,'observed'));
  if(j.description){const listing=el('details');listing.append(el('summary','Listing description'),el('p',j.description,'description'));details.append(listing);}
  card.append(details);panel.append(card);
}
narrow.addEventListener('change',()=>{mobileDetail=false;$('split').classList.remove('show-detail');});
$('job-detail').addEventListener('keydown',event=>{if(event.key==='Escape'&&mobileDetail)$('back').click();});
function options(id,values){const select=$(id);while(select.options.length>1)select.remove(1);for(const value of [...new Set(values)].filter(Boolean).sort())select.add(new Option(value,value));}
function health(){
 const issues=data.health.filter(h=>h.status!=='ok'),healthy=data.health.filter(h=>h.status==='ok');
 $('health-summary').textContent=`${issues.length} coverage issue${issues.length===1?'':'s'} · ${healthy.length} successful checks`;
 const rows=items=>{const box=el('div');for(const h of items){const row=el('div',undefined,'health-row'),name=el('div',h.source);if(h.message)name.append(el('small',h.message));row.append(name,el('span',({ok:'Checked',paused:'Paused',needs_login:'Needs login',limited:'Limited',error:'Error'})[h.status]||h.status,h.status==='ok'?'healthy':'problem'),el('span',h.count===null?'':`${h.count} found`,'quantity'));box.append(row);}return box;};
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
 }catch{data=null;$('error').hidden=false;$('jobs').replaceChildren();showJob();$('empty').hidden=true;$('count').textContent='Job data unavailable';$('updated').textContent='Latest scan could not be loaded';$('health-summary').textContent='Coverage data unavailable';}
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
document.querySelector('a[href="#coverage"]').addEventListener('click',()=>{$('coverage').open=true;});
load();
