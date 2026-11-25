import {test} from 'node:test';
import assert from 'node:assert/strict';
import {dashboardData} from '../src/dashboard.mjs';
import {filterJobs} from '../web/model.mjs';

const a={id:'a',title:'Senior QA Engineer',company:'Cermati',location:'Jakarta',sources:['Cermati'],firstSeen:'2026-11-25T12:00:00Z',triage:{score:90,status:'review',reasons:['Java'],flags:['Salary undisclosed'],rejections:[]}};
const b={...a,id:'b',company:'PayPay',location:'Japan',sources:['PayPay'],triage:{...a.triage,score:70}};
test('filters combine search, source, company, location and score',()=>{
 assert.deepEqual(filterJobs([a,b],{query:'qa',source:'Cermati',company:'Cermati',location:'Jakarta',minScore:80}),[a]);
 assert.equal(filterJobs([a,b],{query:'does not exist'}).length,0);
});
test('excluded roles hidden by default but available on request',()=>{
 const excluded={...a,id:'x',triage:{...a.triage,status:'reject'}};
 assert.equal(filterJobs([a,excluded],{}).length,1);
 assert.equal(filterJobs([a,excluded],{status:'all'}).length,2);
 assert.equal(filterJobs([a,excluded],{status:'reject'}).length,1);
});
test('new-only uses last run time and newest sort handles missing dates',()=>{
 assert.deepEqual(filterJobs([b,{...a,firstSeen:null}],{newOnly:true,updatedAt:a.firstSeen}),[b]);
 assert.equal(filterJobs([{...a,firstSeen:null},b],{sort:'newest'})[0].id,'b');
});
test('export allowlists fields, strips markup, refuses unsafe links',()=>{
 const state={updatedAt:a.firstSeen,health:[{source:'LinkedIn',status:'needs_login',message:'Missing session'}],jobs:{a:{...a,url:'https://example.com/jobs/1',description:'<p>API testing</p>',privateNote:'do not publish'},x:{...b,url:'javascript:alert(1)'}}};
 const d=dashboardData(state);
 assert.equal(d.jobs.length,1);assert.equal(d.jobs[0].description,'API testing');
 assert.equal(d.jobs[0].privateNote,undefined);assert.equal(d.health[0].status,'needs_login');
 assert.equal(d.updatedAt,a.firstSeen);
});
