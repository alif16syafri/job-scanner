export function filterJobs(jobs,filters={}){
 const {query='',source='',company='',location='',minScore=0,status='candidates',newOnly=false,updatedAt,sort='score'}=filters;
 const q=query.trim().toLowerCase();
 return jobs.filter(j=>{
  if(status==='candidates'&&j.triage.status==='reject')return false;
  if(status==='reject'&&j.triage.status!=='reject')return false;
  if(q&&!`${j.title} ${j.company} ${j.location} ${j.description} ${j.triage.reasons.join(' ')}`.toLowerCase().includes(q))return false;
  return (!source||j.sources.includes(source))&&(!company||j.company===company)&&(!location||j.location===location)&&j.triage.score>=Number(minScore)&&(!newOnly||j.firstSeen===updatedAt);
 }).sort((a,b)=>sort==='newest'?((Date.parse(b.firstSeen)||0)-(Date.parse(a.firstSeen)||0)):b.triage.score-a.triage.score||a.company.localeCompare(b.company));
}
