import {createHash} from 'node:crypto';

export function canonical(value) {
 const u=new URL(value); u.hash='';
 for(const key of [...u.searchParams.keys()]) if(/^(utm_|tracking|trk$|ref$|source$|position$|pageNum$)/i.test(key)) u.searchParams.delete(key);
 u.pathname=u.pathname.replace(/\/$/,'');
 return u.toString().replace(/\/$/,'');
}
export const roleMatch=title=>/\b(qa|sdet|software test(er|ing)?|software engineer,? quality|test automation|automation test(er|ing)?|quality assurance|quality engineer|engineer in test|test engineer)\b/i.test(title) && !/manufactur|hardware|civil|food|pharma|electrical|embedded|commissioning|financial crime|underwriting|food safety|quality assurance.*\b(?:kyc|aml)\b/i.test(title);
export function mergeSources(persisted,seeds){return [...new Map([...persisted,...seeds].map(s=>[canonical(s.url),s])).values()];}

export function triage(job) {
 const text=`${job.title} ${job.description||''}`.toLowerCase(), location=(job.location||'').toLowerCase();
 const reasons=[],flags=[],reject=[]; let score=40;
 const softwareTesting=/\b(?:sdet|software testing|test automation|automated tests?|regression testing|api testing|test scripts?)\b/i;
 const operations=/sar reporting|risk (?:&|and) compliance expertise|auditing interactions|audit frontline agent|payment operations|food safety|call quality|hygiene standards/i;
 if(!roleMatch(job.title)||operations.test(text)&&!softwareTesting.test(text)) reject.push('Outside software QA roles');
 if(/\bindia\b|bengaluru|bangalore|mumbai|hyderabad|pune|chennai/.test(location)) reject.push('India location excluded');
 if(/brazil|são paulo|sao paulo|canada|toronto|vancouver|mexico|argentina|colombia|latam|latin america|south africa|nigeria|kenya/.test(location)&&!/remote|worldwide|global/.test(location))reject.push('Onsite location outside target regions');
 if(/must work (?:us|u\.s\.|american)|required.{0,30}(?:us eastern|us pacific|est business|pst business)|(?:us eastern|us pacific) business hours/.test(text)) reject.push('Required US working hours');
 const indonesia=/jakarta|indonesia/.test(location);
 if(indonesia && /contract|freelance|temporary|part.?time/i.test(job.employment||'')) reject.push('Indonesia role is not full-time');
 else if(!job.employment) flags.push('Employment type unverified');
 if(job.validThrough && Number.isFinite(Date.parse(job.validThrough)) && Date.parse(job.validThrough)<Date.now()) reject.push('Application deadline passed');
 if(job.closed) reject.push('Employer listing closed');
 if(/pooling|talent pool|future roles/i.test(job.title)) flags.push('Talent pool; immediate vacancy unconfirmed');
 if(!job.verified) flags.push('Employer details not verified');
 if(!job.location) flags.push('Location unverified');
 if(!indonesia) {
  if(/no visa spons|(?:cannot|do not|not able to|unable to).{0,25}sponsor|sponsorship.{0,12}(?:unavailable|not (?:available|provided))/.test(text))flags.push('Visa sponsorship unavailable; work authorization required');
  else if(!/visa spons|relocation (?:support|assistance)|sponsor.{0,20}visa/i.test(text)) flags.push('Visa / relocation support unverified');
  if(/remote/i.test(location+' '+text) && !/remote.{0,35}(indonesia|worldwide|south.?east asia)|(?:indonesia|worldwide).{0,20}remote/i.test(location+' '+text)) flags.push('Remote country eligibility unverified');
  if(/united states|\busa\b|\bu\.s\./.test(location) && !/indonesia|apac|asynchronous|flexible hours/.test(text)) flags.push('US schedule / Indonesia eligibility unverified');
 }
 if(job.salary?.currency==='IDR' && job.salary.period==='month' && job.salary.basis==='net') {
  if(job.salary.amount<15000000) reject.push('Below IDR 15M monthly net minimum');
  else if(job.salary.amount<16000000) {flags.push('IDR 15–16M net: assess as mid-level exception');score+=3;}
 } else flags.push(job.salary?'Salary needs net-pay / local-cost assessment':'Salary undisclosed');
 for(const [pattern,label,weight] of [[/selenium/,'Selenium',9],[/\bjava\b/,'Java',8],[/cucumber|\bbdd\b/,'BDD / Cucumber',9],[/\bapi\b/,'API testing',7],[/jenkins|ci\/cd/,'CI/CD',6],[/fintech|payments|e-commerce/,'Fintech / commerce',6],[/claude|ai-assisted|ai tools/,'AI-assisted QA',4],[/ios|android/,'Mobile testing',5]]) if(pattern.test(text)){score+=weight;reasons.push(label);}
 if(/jakarta|indonesia|singapore|malaysia|petaling|kuala lumpur/.test(location)){score+=6;reasons.push('Preferred geography');}
 for(const skill of ['playwright','cypress','appium','rest-assured','swift','iso 20022','aws']) if(text.includes(skill)) flags.push(`Check experience: ${skill}`);
 return {status:reject.length?'reject':flags.length?'review':'match',score:Math.min(score,100),reasons,flags,rejections:reject};
}

export function mergeJobs(existing,incoming,now) {
 const result={...existing};
 for(const item of incoming){
  const url=canonical(item.url),id=createHash('sha256').update(url).digest('hex').slice(0,20),old=result[id];
  const job={...old,...item,url,firstSeen:old?.firstSeen||now,lastSeen:now,sources:[...new Set([...(old?.sources||[]),item.source||'unknown'])]};
  // Search snippets must not overwrite a previously fetched employer description.
  if(old?.verified && !item.verified) Object.assign(job,{title:old.title,company:old.company,description:old.description,verified:true,location:old.location,employment:old.employment,salary:old.salary,validThrough:old.validThrough});
  job.triage=triage(job);result[id]=job;
 }
 return result;
}

export function searchPlan(config,cursor=0) {
 const all=config.markets.flatMap(market=>config.roles.map(role=>({key:`${market}|${role}`,market,role,query:`"${role}" "${market}" careers jobs`})));
 const count=Math.min(config.queriesPerRun,all.length);
 return {queries:Array.from({length:count},(_,i)=>all[(cursor+i)%all.length]),nextCursor:(cursor+count)%all.length};
}
