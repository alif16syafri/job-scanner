import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {filterJobs} from '../web/model.mjs';
const require=createRequire(import.meta.url);
const {chromium}=require('playwright');
const root=new URL('../dist',import.meta.url).pathname;
const server=createServer(async(req,res)=>{try{const path=new URL(req.url,'http://localhost').pathname;const file=path==='/'?'index.html':path.slice(1);if(file.includes('..'))throw Error();const b=await readFile(root+'/'+file);res.setHeader('Content-Type',file.endsWith('.mjs')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.json')?'application/json':'text/html');res.end(b);}catch{res.statusCode=404;res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const browser=await chromium.launch({headless:true,executablePath:process.env.DASHBOARD_BROWSER||(process.platform==='darwin'?'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome':undefined)});
const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const url=`http://127.0.0.1:${server.address().port}`;
try{
 await page.goto(url);await page.locator('#jobs[aria-busy="false"]').waitFor();
 const count=await page.locator('.job').count();assert.ok(count>0);console.log('Loaded real jobs:',count);
 const saved=JSON.parse(await readFile(root+'/data.json','utf8'));
 await page.locator('#query').fill('NO-MATCH-1234');assert.equal(await page.locator('.job').count(),0);assert.ok(await page.locator('#empty').isVisible());
 await page.locator('#clear').click();assert.equal(await page.locator('.job').count(),count);
 for(const id of ['company','source','location']){
  const value=await page.locator('#'+id+' option').nth(1).getAttribute('value');await page.locator('#'+id).selectOption(value);assert.equal(await page.locator('.job').count(),filterJobs(saved.jobs,{[id]:value}).length);await page.locator('.reset').click();
 }
 await page.locator('#minScore').selectOption('90');assert.ok(await page.locator('.score strong').evaluateAll(es=>es.every(e=>Number(e.textContent)>=90)));await page.locator('.reset').click();
 await page.locator('#status').selectOption('reject');assert.ok(await page.locator('.status').evaluateAll(es=>es.every(e=>e.textContent.includes('Excluded'))));
 await page.locator('#status').selectOption('all');assert.ok(await page.locator('.job').count()>=count);await page.locator('.reset').click();
 await page.locator('#sort').selectOption('newest');await page.locator('#newOnly').check();await page.locator('.reset').click();
 await page.locator('.job details summary').first().click();assert.ok(await page.locator('.job details[open]').count());
 const href=await page.locator('.job h3 a').first().getAttribute('href');assert.ok(href.startsWith('https://'));
 await page.locator('a[href="#coverage"]').click();assert.ok(await page.locator('#coverage').isVisible());
 await page.locator('.health-group summary').click();assert.ok(await page.locator('.health-group[open]').count());
 await page.screenshot({path:'/tmp/dita-dashboard-desktop.png',fullPage:true});
 await page.locator('#theme').click();assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
 await page.screenshot({path:'/tmp/dita-dashboard-dark.png',fullPage:true});await page.locator('#theme').click();
 for(const width of [390,640,900,1440]){await page.setViewportSize({width,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Overflow at ${width}`);}
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'/tmp/dita-dashboard-mobile.png',fullPage:true});
 await page.route('**/data.json',route=>route.fulfill({status:503,body:'unavailable'}));await page.reload();await page.locator('#error:not([hidden])').waitFor();assert.ok(await page.locator('#retry').isVisible());await page.unroute('**/data.json');await page.locator('#retry').click();await page.locator('.job').first().waitFor();
 await page.keyboard.press('Tab');assert.ok(await page.evaluate(()=>document.activeElement!==document.body));
 assert.deepEqual(errors,[]);console.log('PASS: filters, score/sort, excluded jobs, empty reset, details, health, themes, retry, keyboard focus, 4 viewport widths, no console errors.');
}finally{await browser.close();await new Promise(r=>server.close(r));}
