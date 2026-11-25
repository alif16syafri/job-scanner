import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {existsSync} from 'node:fs';
const execute=promisify(execFile);
export function linkedinUrl(query,seconds=604800){
 return 'https://www.linkedin.com/jobs/search/?'+new URLSearchParams({keywords:query.role,location:query.market,sortBy:'DD',f_TPR:`r${seconds}`,start:'0'});
}
export function linkedinBlocked(url,text){return /\/login|\/authwall|\/checkpoint|\/challenge/.test(url)||/security verification|verify you are human|unusual activity|captcha/i.test(text);}
async function cli(...args){
 const {stdout}=await execute(process.env.PLAYWRIGHT_CLI||'playwright-cli',['-s=dita-discovery','--raw',...args],{timeout:45000,maxBuffer:3000000});
 if(/### Error|isError.*true/.test(stdout))throw Error('Playwright CLI command failed');return stdout.trim();
}
export async function linkedin(queries,config){
 const auth=process.env.LINKEDIN_STATE_PATH||'.secrets/linkedin.json';
 if(!existsSync(auth))return {jobs:[],status:'needs_login',message:'LinkedIn session missing; save browser state and configure LINKEDIN_STATE_B64'};
 const jobs=[];
 try{
  await cli('open','about:blank','--browser','chrome');
  await cli('state-load',auth);
  for(const query of queries){
   await cli('goto',linkedinUrl(query,config.lookbackSeconds));
   await cli('run-code',"await page.waitForSelector('a[href*=\"/jobs/view/\"], .jobs-search-no-results-banner, .jobs-search-no-results, input[name=\"session_key\"], iframe[src*=\"captcha\"]', {timeout: 15000}).catch(() => {});");
   const raw=await cli('eval',`() => ({url:location.href,text:document.body.innerText.slice(0,12000),jobs:[...document.querySelectorAll('a[href*="/jobs/view/"]')].map(a=>{const card=a.closest('li')||a.parentElement;return {url:a.href,title:(a.querySelector('strong')?.innerText||a.innerText||a.getAttribute('aria-label')||'').trim().split('\\n')[0],company:(card.querySelector('.job-card-container__primary-description,.base-search-card__subtitle')?.textContent||'Unverified').trim(),location:(card.querySelector('.job-card-container__metadata-item,.job-search-card__location')?.textContent||'').trim(),description:card.innerText.slice(0,2500),datePosted:card.querySelector('time')?.getAttribute('datetime')||null}})})`);
   let page;try{page=JSON.parse(raw);if(typeof page==='string')page=JSON.parse(page);}catch{throw Error('Unexpected LinkedIn CLI output');}
   if(linkedinBlocked(page.url,page.text))return {jobs,status:'needs_login',message:'LinkedIn login or access challenge; stopped without bypassing'};
   if(!page.jobs.length&&!/no (?:matching )?(?:jobs|results)|0 results/i.test(page.text))return {jobs,status:'error',message:'LinkedIn page unreadable; selector or access check required'};
   jobs.push(...page.jobs.filter(j=>j.title).slice(0,config.maxSearchResults).map(j=>({...j,source:'LinkedIn',verified:false,searchMarket:query.market})));
  }
  return {jobs,status:'ok',message:`${queries.length} searches; first visible result page per query`};
 }catch{return {jobs,status:'error',message:'LinkedIn CLI failed; inspect browser setup/session locally (session output is not logged)'};}
 finally{await cli('close').catch(()=>{});}
}
