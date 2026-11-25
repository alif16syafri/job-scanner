import {test} from 'node:test';
import assert from 'node:assert/strict';
import {triage, canonical, mergeJobs, searchPlan, mergeSources} from '../src/core.mjs';

const job = (extra={}) => ({title:'QA Engineer',company:'Example',location:'Jakarta',description:'Full-time Java Selenium API testing',url:'https://example.com/jobs/1',...extra});
test('gross salary is not treated as take-home salary',()=>{
 assert.equal(triage(job({salary:{amount:15000000,currency:'IDR',period:'month',basis:'gross'}})).status,'review');
 assert.equal(triage(job({salary:{amount:14000000,currency:'IDR',period:'month',basis:'net'}})).status,'reject');
 assert.notEqual(triage(job({salary:{amount:15000000,currency:'IDR',period:'month',basis:'net'}})).status,'reject');
});
test('India excluded but Indonesia is not, and India office boilerplate is not a location',()=>{
 assert.equal(triage(job({location:'Bengaluru, India'})).status,'reject');
 assert.notEqual(triage(job({description:'Full-time Java. Offices in India and Indonesia.'})).status,'reject');
});
test('US headquarters alone does not reject a compatible role',()=>{
 assert.notEqual(triage(job({description:'US company. Full-time remote from Indonesia, flexible hours.'})).status,'reject');
 assert.equal(triage(job({description:'Must work US Eastern business hours. Full-time.'})).status,'reject');
});
test('remote is never assumed to permit Indonesia or sponsorship',()=>{
 const result=triage(job({location:'Remote, United Kingdom',description:'Full-time remote Java testing'}));
 assert.ok(result.flags.includes('Remote country eligibility unverified'));
 assert.ok(result.flags.includes('Visa / relocation support unverified'));
});
test('QA manufacturing rejected and manual software QA included',()=>{
 assert.equal(triage(job({title:'Manufacturing Quality Engineer'})).status,'reject');
 assert.notEqual(triage(job({title:'Manual Software Tester'})).status,'reject');
});
test('contract in Indonesia rejected; overseas contract retained',()=>{
 assert.equal(triage(job({employment:'CONTRACTOR'})).status,'reject');
 assert.notEqual(triage(job({location:'Singapore',employment:'CONTRACTOR'})).status,'reject');
});
test('explicit expiry rejects but missing dates remain unknown',()=>{
 assert.equal(triage(job({validThrough:'2020-01-01'})).status,'reject');
 assert.notEqual(triage(job()).status,'reject');
});
test('dedupe strips tracking, preserves identity parameters and first seen',()=>{
 assert.equal(canonical('https://www.linkedin.com/jobs/view/123/?trackingId=abc'),'https://www.linkedin.com/jobs/view/123');
 assert.notEqual(canonical('https://x.com/job?id=1'),canonical('https://x.com/job?id=2'));
 let state=mergeJobs({},[job()], '2026-11-01');
 state=mergeJobs(state,[job({url:'https://example.com/jobs/1?utm_source=x',description:'updated'})], '2026-11-02');
 assert.equal(Object.keys(state).length,1);
 assert.equal(Object.values(state)[0].firstSeen,'2026-11-01');
 assert.equal(Object.values(state)[0].lastSeen,'2026-11-02');
});
test('rotating search plan covers every configured role and market',()=>{
 const config={roles:['QA Engineer','SDET'],markets:['Jakarta','Singapore','Dubai'],queriesPerRun:2};
 const plans=[0,2,4].flatMap(cursor=>searchPlan(config,cursor).queries);
 assert.equal(new Set(plans.map(q=>q.key)).size,6);
 assert.notDeepEqual(searchPlan(config,0).queries,searchPlan(config,2).queries);
});
test('negative sponsorship language remains an eligibility warning',()=>{
 const r=triage(job({location:'Singapore',description:'Full-time. No visa sponsorship available.'}));
 assert.ok(r.flags.some(f=>/sponsorship unavailable/i.test(f)));
});
test('onsite locations outside target regions rejected, regional codes recognized',()=>{
 assert.equal(triage(job({location:'São Paulo, Brazil'})).status,'reject');
 assert.notEqual(triage(job({location:'SG'})).status,'reject');
});
test('configured seed adapters override stale persisted settings',()=>{
 assert.equal(mergeSources([{url:'https://example.com/jobs',kind:'html'}],[{url:'https://example.com/jobs',kind:'workable'}])[0].kind,'workable');
});
