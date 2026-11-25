import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parsePage, safeUrl, parseSearch} from '../src/sources.mjs';
test('JSON-LD job retains location, salary basis unknown, and deadline',()=>{
 const html='<script type="application/ld+json">'+JSON.stringify({'@type':'JobPosting',title:'QA Engineer',description:'Java API',hiringOrganization:{name:'Acme'},jobLocation:{address:{addressLocality:'Jakarta',addressCountry:'ID'}},employmentType:'FULL_TIME',validThrough:'2027-01-01',baseSalary:{currency:'IDR',value:{minValue:16000000,unitText:'MONTH'}}})+'</script>';
 const result=parsePage(html,'https://example.com/jobs/1','Acme');
 assert.equal(result.jobs[0].company,'Acme');assert.match(result.jobs[0].location,/Jakarta/);assert.equal(result.jobs[0].salary.basis,'unknown');assert.equal(result.jobs[0].validThrough,'2027-01-01');
});
test('empty JavaScript shell is failure, never successful zero jobs',()=>{
 assert.throws(()=>parsePage('<div id="app"></div>','https://example.com/careers','Example'),/No readable/);
});
test('career links include newly discovered employers but not unrelated pages',()=>{
 const result=parsePage('<h1>Careers</h1><a href="/jobs/123">Senior QA Engineer</a><a href="/privacy">Privacy</a>','https://example.com/careers','Example');
 assert.deepEqual(result.links,['https://example.com/jobs/123']);
});
test('search RSS handles escaped HTML and records unverified results',()=>{
 const results=parseSearch('<rss><channel><item><title>QA Engineer - Acme</title><link>https://example.com/jobs/1</link><description>Jakarta &amp; Remote</description></item></channel></rss>');
 assert.equal(results.length,1);assert.equal(results[0].verified,false);
});
test('URLs discovered externally cannot fetch private hosts or credentials',()=>{
 for(const u of ['http://127.0.0.1/a','https://169.254.169.254/a','https://localhost/a','https://10.1.1.1/a','https://user:pass@example.com/a','file:///etc/passwd','https://[::1]/']) assert.throws(()=>safeUrl(u));
 assert.equal(safeUrl('https://careers.example.com/jobs'),'https://careers.example.com/jobs');
});
test('search excludes educational QA articles and course providers',()=>{
 const xml='<rss><channel><item><title>What is Quality Assurance (QA)?</title><link>https://example.com/blog/qa</link></item><item><title>QA Engineer</title><link>https://example.com/jobs/123</link></item></channel></rss>';
 assert.equal(parseSearch(xml).length,1);
});
test('generic QA article is not verified as an employer vacancy',()=>{
 assert.throws(()=>parsePage('<h1>Software Quality Assurance</h1><main>Learn QA with our course</main>','https://example.com/course/qa','Example'));
});
test('multiple JSON-LD jobs preserve individual canonical URLs',()=>{
 const h='<script type="application/ld+json">'+JSON.stringify([{'@type':'JobPosting',title:'QA Engineer',url:'/jobs/1'},{'@type':'JobPosting',title:'SDET',url:'/jobs/2'}])+'</script>';
 assert.deepEqual(parsePage(h,'https://example.com/careers','Example').jobs.map(j=>j.url),['https://example.com/jobs/1','https://example.com/jobs/2']);
});
test('navigation-only career shell is not successful zero coverage',()=>{
 assert.throws(()=>parsePage('<nav><a href="/jobs">Jobs</a><a href="/careers">Careers</a></nav><div id="app"></div>','https://example.com/jobs','Example'),/No readable/);
});
