import {test} from 'node:test';
import assert from 'node:assert/strict';
import {linkedinUrl,linkedinBlocked} from '../src/linkedin.mjs';
test('LinkedIn search preserves role, market, latest sort and lookback',()=>{
 const u=new URL(linkedinUrl({role:'QA Engineer',market:'Singapore'}));
 assert.equal(u.searchParams.get('location'),'Singapore');assert.equal(u.searchParams.get('sortBy'),'DD');assert.equal(u.searchParams.get('f_TPR'),'r604800');
});
test('login and challenge interrupt discovery, not ordinary job text',()=>{
 assert.ok(linkedinBlocked('https://www.linkedin.com/checkpoint/abc',''));
 assert.ok(linkedinBlocked('https://www.linkedin.com/jobs','Security verification'));
 assert.equal(linkedinBlocked('https://www.linkedin.com/jobs','QA jobs in Singapore'),false);
});
