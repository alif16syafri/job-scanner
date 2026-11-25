import {execFile} from 'node:child_process';
import {mkdtemp,readFile,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {promisify} from 'node:util';

const execute=promisify(execFile);
const bundledCli=fileURLToPath(new URL('../node_modules/.bin/playwright-cli',import.meta.url));

export function linkedinUrl({role,market},seconds=604800){
 const remote=market.endsWith(' remote');
 const location=remote?market.slice(0,-' remote'.length):market;
 const params=new URLSearchParams({keywords:role,location,sortBy:'DD',f_TPR:`r${seconds}`});
 if(location==='Jakarta'||location==='Indonesia')params.set('f_JT','F');
 if(remote)params.set('f_WT','2');
 return 'https://www.linkedin.com/jobs/search/?'+params;
}

export function linkedinBlocked(url,text){
 return /\/(?:login|authwall|checkpoint|challenge|uas\/login)(?:[/?#]|$)/i.test(url)
  || /security verification|verify you are human|unusual activity|captcha/i.test(text);
}

function readListings(){
 const jobs=new Map();
 const content=(node,selectors)=>node.querySelector(selectors)?.textContent.trim()||'';
 for(const link of document.querySelectorAll('a[href*="/jobs/view/"]')){
  const path=new URL(link.href).pathname;
  const id=path.match(/^\/jobs\/view\/(?:[^/]+-)?(\d+)\/?$/)?.[1];
  if(!id||jobs.has(id))continue;
  const card=link.closest('[data-job-id],li,.base-card')||link.parentElement;
  const title=content(card,'.base-search-card__title, .job-card-list__title--link strong, .job-card-container__link strong')
   ||link.getAttribute('aria-label')||link.textContent.trim().split('\n')[0].trim();
  if(!title)continue;
  jobs.set(id,{
   url:`https://www.linkedin.com/jobs/view/${id}/`,
   title,
   company:content(card,'.base-search-card__subtitle, .job-card-container__primary-description')||'Unverified',
   location:content(card,'.job-search-card__location, .job-card-container__metadata-item'),
   description:content(card,'.job-search-card__snippet, .job-card-list__description'),
   datePosted:card.querySelector('time')?.getAttribute('datetime')||null
  });
 }
 return {
  url:location.href,
  text:document.body?.innerText.slice(0,4000)||'',
  signedIn:!!document.querySelector('#global-nav, .global-nav__content, .global-nav__me'),
  jobs:[...jobs.values()]
 };
}

export async function linkedin(queries,config){
 const {LINKEDIN_STATE_B64,LINKEDIN_STATE_PATH, ...browserEnv}=process.env;
 let state;
 try{
  const input=LINKEDIN_STATE_PATH
   ? await readFile(LINKEDIN_STATE_PATH,'utf8')
   : LINKEDIN_STATE_B64
    ? Buffer.from(LINKEDIN_STATE_B64,'base64').toString('utf8')
    : await readFile('.secrets/linkedin.json','utf8');
  state=JSON.parse(input);
  state={
   cookies:state.cookies.filter(cookie=>/(^|\.)linkedin\.com$/i.test(cookie.domain)),
   origins:state.origins.filter(origin=>new URL(origin.origin).hostname==='www.linkedin.com')
  };
  if(!state.cookies.some(cookie=>cookie.name==='li_at'&&cookie.value))throw Error('Missing LinkedIn login');
 }catch{
  return {jobs:[],status:'needs_login',message:'Dita’s LinkedIn session is missing or invalid. Other sources still run.'};
 }
 const cwd=await mkdtemp(join(tmpdir(),'job-scanner-linkedin-'));
 const configuredCli=process.env.PLAYWRIGHT_CLI;
 const binary=configuredCli?.includes('/')?resolve(configuredCli):configuredCli||bundledCli;
 async function cli(...args){
  const {stdout}=await execute(binary,['-s=linkedin-headless','--raw',...args],{
   cwd,env:browserEnv,timeout:40000,maxBuffer:3_000_000
  });
  if(/^### Error/m.test(stdout))throw Error('Playwright CLI command failed');
  return stdout.trim();
 }
 const jobs=new Map();
 let checked=0;
 let failure='';
 let opened=false;
 const result=(status,message)=>({jobs:[...jobs.values()],status,message});
 try{
  const stateFile=join(cwd,'linkedin.json');
  await writeFile(stateFile,JSON.stringify(state),{mode:0o600});
  await cli('open','about:blank');
  opened=true;
  await cli('state-load',stateFile);
  await rm(stateFile,{force:true});
  for(const query of queries){
   try{
    const url=linkedinUrl(query,config.lookbackSeconds);
    const raw=await cli('run-code',`async page => {
     const response=await page.goto(${JSON.stringify(url)},{timeout:20000,waitUntil:'domcontentloaded'});
     const status=response?.status()||0;
     if(status>=400)return {status};
     await page.locator('a[href*="/jobs/view/"], .jobs-search-no-results-banner, .jobs-search-no-results, .no-results, input[name="session_key"], iframe[src*="captcha"]').first()
      .waitFor({state:'attached',timeout:6000}).catch(()=>{});
     return {status,...await page.evaluate(${readListings.toString()})};
    }`);
    const page=JSON.parse(raw);
    if(page.status===429||page.status===999||page.status===403)return result('limited',`LinkedIn denied or rate-limited the headless request (HTTP ${page.status}).`);
    if(page.status>=400){
     failure=`LinkedIn returned HTTP ${page.status}.`;
     continue;
    }
    if(linkedinBlocked(page.url,page.text)||!page.signedIn)return result('needs_login','LinkedIn did not show a signed-in Jobs page. Session may need renewal or verification.');
    if(!page.jobs.length&&!/no (?:matching )?(?:jobs|results)|0 results/i.test(page.text)){
     failure='LinkedIn returned no readable job cards or explicit empty state.';
     continue;
    }
    checked++;
    for(const job of page.jobs.slice(0,config.maxSearchResults)){
     jobs.set(job.url,{...job,source:'LinkedIn',verified:false,searchMarket:query.market});
    }
   }catch{
    failure='Playwright could not read one or more LinkedIn searches.';
   }
  }
  const summary=`Signed-in headless search checked ${checked} of ${queries.length} filtered searches.`;
  return result(failure?(checked?'limited':'error'):'ok',failure?`${summary} ${failure}`:summary);
 }catch{
  return result('error',opened?'Playwright could not load the saved LinkedIn session.':'Headless Playwright could not start. Install the Chromium headless shell.');
 }finally{
  await cli('close').catch(()=>{});
  await rm(cwd,{recursive:true,force:true});
 }
}
