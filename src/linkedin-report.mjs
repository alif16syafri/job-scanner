export function localLinkedinReport(report){
 const time=Date.parse(report.scannedAt);
 if(!Number.isFinite(time)||time>Date.now()+600000||!Array.isArray(report.jobs)){
  throw Error('Invalid Mac LinkedIn report.');
 }
 const cleaned=value=>typeof value==='string'?value.trim().slice(0,300):'';
 const jobs=report.jobs.slice(0,1500).flatMap(job=>{
  const id=typeof job?.url==='string'&&job.url.match(/^https:\/\/www\.linkedin\.com\/jobs\/view\/(\d+)\/?$/)?.[1];
  if(!id||!cleaned(job.title))return [];
  return [{url:`https://www.linkedin.com/jobs/view/${id}`,title:cleaned(job.title),
   company:cleaned(job.company),location:cleaned(job.location),searchMarket:cleaned(job.searchMarket),
   datePosted:/^\d{4}-\d{2}-\d{2}$/.test(job.datePosted)?job.datePosted:null,source:'LinkedIn',verified:false}];
 });
 return {scannedAt:new Date(time).toISOString(),status:['ok','limited','error','needs_login'].includes(report.status)?report.status:'error',
  message:cleaned(report.message),jobs};
}
