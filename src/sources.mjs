import * as cheerio from 'cheerio';
import {lookup} from 'node:dns/promises';
import {isIP} from 'node:net';
import {roleMatch,canonical} from './core.mjs';

const linkedinHost=/(^|\.)linkedin\.com$/i;

export function safeUrl(value){
 const u=new URL(value);
 if(linkedinHost.test(u.hostname)||u.protocol!=='https:'||u.username||u.password||u.port&&!['443'].includes(u.port)||isIP(u.hostname.replace(/[\[\]]/g,''))||!u.hostname.includes('.')||/\.(local|internal|localhost)$/.test(u.hostname)) throw Error('Unsafe source URL');
 return u.toString();
}
function publicAddress(address){return !/^(0\.|10\.|127\.|169\.254\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.|::|f[cd]|fe[89ab])/i.test(address);}
export async function get(url,headers={},depth=0){
 safeUrl(url);
 const addresses=await lookup(new URL(url).hostname,{all:true});
 if(!addresses.length||addresses.some(x=>!publicAddress(x.address)))throw Error('Private source address refused');
 const res=await fetch(url,{headers:{'User-Agent':'DitaJobDiscovery/1.0',...headers},signal:AbortSignal.timeout(25000),redirect:'manual'});
 if([301,302,303,307,308].includes(res.status)) {if(depth>=4)throw Error('Too many redirects');return get(new URL(res.headers.get('location'),url).href,{},depth+1);}
 if(!res.ok)throw Error(`HTTP ${res.status}`);
 const body=await res.text();if(body.length>5000000)throw Error('Source response too large');return body;
}
function plain(value){const $=cheerio.load(String(value||''));return $.text().replace(/\s+/g,' ').trim();}
export function jobUrl(url){try{const u=new URL(url);return !linkedinHost.test(u.hostname)&&!/\/blog|\/articles?|\/wiki|\/courses?|\/learn|\/training|\/career-advice|\/career-guide|\/guides?\//i.test(u.pathname)&&(/jobs|careers|career|apply|vacanc|roles|positions|recruit/i.test(u.hostname+u.pathname));}catch{return false;}}
function jobFromLd(j,url,name){
 if(j.url)url=safeUrl(new URL(j.url,url).href);
 const locations=[j.jobLocation].flat().filter(Boolean).map(l=>{const a=l.address||{};return [a.addressLocality,a.addressRegion,typeof a.addressCountry==='object'?a.addressCountry.name:a.addressCountry].filter(Boolean).join(', ');});
 if(j.jobLocationType==='TELECOMMUTE') locations.push('Remote');
 const restrictions=[j.applicantLocationRequirements].flat().filter(Boolean).map(x=>x.name).filter(Boolean);
 const s=j.baseSalary,v=s?.value;
 return {title:j.title||'',company:j.hiringOrganization?.name||name,location:[...locations,...restrictions].join('; '),description:plain(j.description),url,employment:[j.employmentType].flat().filter(Boolean).join(', '),datePosted:j.datePosted||null,validThrough:j.validThrough||null,verified:true,salary:v&&typeof v==='object'?{amount:v.minValue??v.value,currency:s.currency,period:/month/i.test(v.unitText)?'month':v.unitText,basis:'unknown'}:null};
}
export function parsePage(html,url,name){
 const $=cheerio.load(html),jobs=[],links=[];
 function visit(value){if(Array.isArray(value))return value.forEach(visit);if(!value||typeof value!=='object')return;if([value['@type']].flat().includes('JobPosting'))jobs.push(jobFromLd(value,url,name));if(value['@graph'])visit(value['@graph']);}
 $('script[type="application/ld+json"]').each((_,s)=>{try{visit(JSON.parse($(s).html()));}catch{}});
 $('nav,footer,header').remove();
 $('a[href]').each((_,a)=>{const title=$(a).text().trim(),href=$(a).attr('href');if(roleMatch(title)){try{links.push(safeUrl(new URL(href,url).href));}catch{}}});
 $('script,style,nav,footer,header').remove();
 const title=$('h1,h2,h3').toArray().map(e=>$(e).text().trim()).find(roleMatch)||$('title').text().split('|')[0].replace(/^Brankas\s*-\s*/,''),description=$('main').text().trim()||$('body').text().trim();
 if(!jobs.length && roleMatch(title)&&jobUrl(url)&&/apply|responsibilit|qualifications|requirements|full.?time|fulltime/i.test(description)) jobs.push({title,company:name,location:'',description:plain(description),url,verified:true});
 const hasListingLinks=$('a[href]').toArray().some(a=>/\/jobs\/[^/?#]+/.test($(a).attr('href')));
 if(!jobs.length&&!links.length&&!hasListingLinks)throw Error('No readable job records or career links; source may require browser rendering');
 return {jobs,links:[...new Set(links)]};
}
export function parseSearch(xml){
 const $=cheerio.load(xml,{xmlMode:true});
 return $('item').toArray().map(item=>({title:$(item).find('title').text(),url:$(item).find('link').text(),description:$(item).find('description').text(),company:'Unverified',location:'',verified:false,source:'web-search'})).filter(j=>roleMatch(j.title)&&jobUrl(j.url));
}
export async function webSearch(query){
 if(process.env.BRAVE_SEARCH_API_KEY){
  const data=JSON.parse(await get(`https://api.search.brave.com/res/v1/web/search?${new URLSearchParams({q:query,count:'10'})}`,{'X-Subscription-Token':process.env.BRAVE_SEARCH_API_KEY}));
  return (data.web?.results||[]).filter(r=>roleMatch(r.title)&&jobUrl(r.url)).map(r=>({title:plain(r.title),url:r.url,description:plain(r.description),company:'Unverified',location:'',verified:false,source:'web-search'}));
 }
 const xml=await get(`https://www.bing.com/search?${new URLSearchParams({q:query,format:'rss'})}`);
 if(!xml.includes('<rss'))throw Error('Search returned no RSS feed');return parseSearch(xml);
}
export async function employer(source){
 if(source.kind==='stockbit'){
  const links=[];
  for(let page=1;page<=20;page++){
   const html=await get(`${source.url}?page=${page}`),$=cheerio.load(html),cards=$('a[href]').toArray().filter(a=>/^\/jobs\/\d+/.test($(a).attr('href')));
   for(const card of cards)if(roleMatch($(card).text()))links.push(new URL($(card).attr('href'),source.url).href);
   if(cards.length<10)break;if(page===20)throw Error('Stockbit pagination budget reached');
  }
  return {jobs:[],links:[...new Set(links)]};
 }
 if(source.kind==='breezy'){
  const data=JSON.parse(await get(`https://${source.board}.breezy.hr/json`));
  if(!Array.isArray(data))throw Error('Unexpected Breezy feed');
  return {jobs:data.filter(j=>roleMatch(j.name)).map(j=>({title:j.name,company:source.name,location:j.location?.name||'',description:plain(j.description),url:j.url,employment:j.type?.name||'',verified:true,source:source.name})),links:[]};
 }
 if(source.kind==='workable'){
  let token=null,all=[];
  for(let page=0;page<20;page++){
   const url=`https://apply.workable.com/api/v3/accounts/${source.board}/jobs`;
   const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(token?{token}:{}),signal:AbortSignal.timeout(25000),redirect:'error'});
   if(!res.ok)throw Error(`Workable HTTP ${res.status}`);const d=await res.json();if(!Array.isArray(d.results))throw Error('Unexpected Workable feed');all.push(...d.results);token=d.nextPage;if(!token)break;if(page===19)throw Error('Workable pagination budget reached');
  }
  return {jobs:all.filter(j=>roleMatch(j.title)).map(j=>({title:j.title,company:source.name,location:(j.locations||[j.location]).filter(Boolean).map(l=>[l.city,l.country].filter(Boolean).join(', ')).join('; '),description:'',employment:j.type==='full'?'Full-time':j.type,url:`https://apply.workable.com/${source.board}/j/${j.shortcode}/`,datePosted:j.published,verified:false,source:source.name})),links:[]};
 }
 if(source.kind==='smart-detail'){
  const d=JSON.parse(await get(`https://api.smartrecruiters.com/v1/companies/${source.board}/postings/${source.id}`));
  return {jobs:[{title:d.name,company:source.name,location:[d.location?.city,d.location?.country].filter(Boolean).join(', '),description:plain(Object.values(d.jobAd?.sections||{}).map(s=>s.text).join(' ')),employment:d.typeOfEmployment?.label||'',url:source.url,verified:true,source:source.name}],links:[]};
 }
 if(source.kind==='workable-detail'){
  const d=JSON.parse(await get(`https://apply.workable.com/api/v2/accounts/${source.board}/jobs/${source.id}`));
  return {jobs:[{title:d.title,company:source.name,location:(d.locations||[d.location]).filter(Boolean).map(l=>[l.city,l.country].filter(Boolean).join(', ')).join('; '),description:plain([d.description,d.requirements,d.benefits].join(' ')),employment:d.type==='full'?'Full-time':d.type,url:source.url,datePosted:d.published,verified:true,source:source.name}],links:[]};
 }
 if(source.kind==='ashby'){
  const board=encodeURIComponent(source.board);
  const data=JSON.parse(await get(`https://api.ashbyhq.com/posting-api/job-board/${board}`));
  if(!Array.isArray(data.jobs))throw Error('Unexpected Ashby response');
  const jobs=data.jobs.filter(j=>j.isListed===true&&roleMatch(j.title)).map(j=>({
   title:j.title,company:source.name,url:safeUrl(j.jobUrl),verified:true,source:source.name,
   location:[j.location,...(j.secondaryLocations||[]).map(place=>place.location),j.workplaceType==='Remote'?'Remote':''].filter(Boolean).join('; '),
   description:j.descriptionPlain||plain(j.descriptionHtml),datePosted:j.publishedAt||null,
   employment:({FullTime:'Full-time',PartTime:'Part-time'})[j.employmentType]||j.employmentType||''
  }));
  return {jobs,links:[]};
 }
 if(source.kind==='greenhouse'){
  const data=JSON.parse(await get(`https://boards-api.greenhouse.io/v1/boards/${source.board}/jobs?content=true`));
  if(!Array.isArray(data.jobs))throw Error('Unexpected Greenhouse response');
  return {jobs:data.jobs.filter(j=>roleMatch(j.title)).map(j=>({title:j.title,company:source.name,location:j.location?.name||'',description:plain(j.content),url:j.absolute_url,verified:true,source:source.name,datePosted:null})),links:[]};
 }
 if(source.kind==='smartrecruiters'){
  let offset=0,all=[];
  while(offset<1000){const d=JSON.parse(await get(`https://api.smartrecruiters.com/v1/companies/${source.board}/postings?limit=100&offset=${offset}`));if(!Array.isArray(d.content))throw Error('Unexpected SmartRecruiters response');all.push(...d.content);if(all.length>=d.totalFound||!d.content.length)break;offset+=100;}
  if(offset>=1000)throw Error('SmartRecruiters pagination budget reached');
  return {jobs:all.filter(j=>roleMatch(j.name)).map(j=>({title:j.name,company:source.name,location:[j.location?.city,j.location?.country].filter(Boolean).join(', '),employment:j.typeOfEmployment?.label||'',description:'',url:`https://jobs.smartrecruiters.com/${source.board}/${j.id}`,datePosted:j.releasedDate,verified:false,source:source.name})),links:[]};
 }
 const u=new URL(source.url),parts=u.pathname.split('/').filter(Boolean);
 if(u.hostname==='jobs.smartrecruiters.com'&&parts.length>1){const id=parts[1].match(/^\d+/)?.[0];if(id)return employer({...source,kind:'smart-detail',board:parts[0],id});}
 if(u.hostname==='apply.workable.com'&&parts[1]==='j'&&parts[2])return employer({...source,kind:'workable-detail',board:parts[0],id:parts[2]});
 return parsePage(await get(source.url),source.url,source.name);
}
export function sourceFor(url){
 const candidate=new URL(url);
 if(linkedinHost.test(candidate.hostname)||/(^|\.)bing\.com$/.test(candidate.hostname))return null;
 const u=new URL(safeUrl(url)),parts=u.pathname.split('/').filter(Boolean);
 if(u.hostname==='jobs.ashbyhq.com'&&parts[0])return {name:parts[0],url:`https://${u.hostname}/${parts[0]}`,kind:'ashby',board:parts[0]};
 if(u.hostname==='job-boards.greenhouse.io'&&parts[0])return {name:parts[0],url:`https://${u.hostname}/${parts[0]}`,kind:'greenhouse',board:parts[0]};
 if(u.hostname==='jobs.smartrecruiters.com'&&parts[0])return {name:parts[0],url:`https://${u.hostname}/${parts[0]}`,kind:'smartrecruiters',board:parts[0]};
 if(u.hostname==='apply.workable.com'&&parts[0])return {name:parts[0],url:`https://${u.hostname}/${parts[0]}/`,kind:'workable',board:parts[0]};
 // A discovered job URL remains a source until its employer index can be established.
 return {name:u.hostname,url:canonical(url),kind:'html'};
}
