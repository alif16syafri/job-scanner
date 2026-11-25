import {test} from 'node:test';
import assert from 'node:assert/strict';
import {localLinkedinReport} from '../src/linkedin-report.mjs';
import {mergeJobs} from '../src/core.mjs';

test('Mac sync keeps only public listing fields and deduplicates replayed jobs',()=>{
 const scannedAt=new Date().toISOString();
 const report=localLinkedinReport({scannedAt,status:'ok',message:'Scan complete',jobs:[
  {url:'https://www.linkedin.com/jobs/view/1234/',title:'QA Engineer',company:'Example',
   location:'Jakarta',description:'Private page text',session:'session value',datePosted:'2026-11-25'},
  {url:'https://www.linkedin.com/in/example/',title:'Not a job'}
 ]});
 assert.equal(report.jobs.length,1);
 assert.deepEqual(Object.keys(report.jobs[0]),['url','title','company','location','searchMarket','datePosted','source','verified']);
 const jobs=mergeJobs({},report.jobs,scannedAt);
 assert.equal(Object.keys(mergeJobs(jobs,report.jobs,scannedAt)).length,1);
});
