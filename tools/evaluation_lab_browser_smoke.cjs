// Optional real-browser check; use a fresh temporary Lab database. Existing Playwright/Chromium required.
const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
 const target=process.argv[2] || 'http://127.0.0.1:8891/';
 const parsed=new URL(target);if(!['127.0.0.1','localhost'].includes(parsed.hostname))throw new Error('loopback test target required');
 const output=process.argv[3] || '/tmp/evaluation-lab-browser-artifacts';fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH || '/usr/bin/chromium',args:process.env.EVALUATION_LAB_BROWSER_NO_SANDBOX === '1' ? ['--no-sandbox'] : []});
 try {
 const page=await browser.newPage({viewport:{width:1440,height:1050}});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(target);
 const initial=await page.evaluate(async()=>await(await fetch('/api/records')).json());if(initial.records.length)throw new Error('Use a fresh temporary database; existing user records are protected');
 await page.waitForSelector('#case option[value="T1"]',{state:'attached'});
 await page.click('#check-models');await page.waitForFunction(()=>document.querySelector('#connection').textContent!=='未检查');
 const ollamaStatus=await page.locator('#connection').innerText();
 await page.selectOption('#provider','mock');await page.selectOption('#case','T1');await page.click('#run');
 await page.waitForFunction(()=>document.querySelector('#outcome').textContent==='ACCEPTED');

 await page.screenshot({path:output+'/single-evaluation.png',fullPage:true});
 await page.click('[data-tab="batch"]');await page.click('#run-batch');
 await page.waitForFunction(()=>document.querySelector('#batch-state').textContent==='COMPLETED · 12/12');
 await page.screenshot({path:output+'/batch-evaluation.png',fullPage:true});
 await page.click('[data-tab="statistics"]');await page.waitForSelector('.metric-grid');
 const statistics=await page.locator('#statistics').innerText();
 if(!statistics.includes('未评 / 无样本'))throw new Error('unannotated semantic metrics should remain unavailable');
 await page.screenshot({path:output+'/statistics.png',fullPage:true});
 await page.click('[data-tab="history"]');await page.waitForSelector('#history button');
 await page.locator('#history button').first().click();await page.waitForSelector('#annotation-panel:not([hidden])');
 if(await page.locator('#annotation-confirmed').isChecked())throw new Error('annotation must never be auto-confirmed');
 const records=await page.evaluate(async()=>await(await fetch('/api/records')).json());
 if(records.records.length!==13||records.records.some(r=>r.source!=='MOCK'||r.annotation!==null||r.safety_result.executable))throw new Error('history/source/annotation boundary failed');
 await page.setViewportSize({width:390,height:844});await page.click('[data-tab="evaluate"]');
 await page.screenshot({path:output+'/mobile.png',fullPage:true});
 const report={browser:'system Chromium / Playwright',single:'ACCEPTED (MOCK)',batch_completed:12,history_records:13,annotations_created:0,real_model_runs:0,ollama_status:ollamaStatus,page_errors:errors};
 fs.writeFileSync(output+'/browser-result.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 if(errors.length)process.exitCode=1;
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
