import {chromium} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
const folder=process.argv[2]||'artifacts/design-review';
await mkdir(folder,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
await context.route('**/*',route=>{const url=new URL(route.request().url());return url.hostname==='127.0.0.1'||url.protocol==='data:'?route.continue():route.abort();});
await context.route('**/api/session',route=>route.fulfill({json:{authenticated:true,isAdmin:true,user:{name:'Alex Morgan',email:'design-review@example.test'}}}));
const page=await context.newPage();
const errors=[];page.on('pageerror',error=>errors.push(error.message));
const routes=[['Compare Companies','compare'],['Stock Analytics','stock'],['Indicators & VSA','indicators'],['Investment Research','research'],['Trade Planner','trade'],['Portfolio Monitor','portfolio'],['Company News','news'],['Event Scenarios','events'],['Macro Regime Monitor','macro']];
await page.goto('http://127.0.0.1:5173/',{waitUntil:'domcontentloaded',timeout:30000});
await page.getByRole('navigation',{name:'Main navigation'}).waitFor({timeout:20000});
await page.waitForTimeout(1200);
await page.screenshot({path:`${folder}/dashboard.png`,fullPage:true});
for(const [name,file] of routes){
 await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true}).click();
 await page.waitForTimeout(900);await page.screenshot({path:`${folder}/${file}.png`,fullPage:true});
}
await page.evaluate(()=>document.documentElement.dataset.theme='dark');
await page.screenshot({path:`${folder}/dark.png`,fullPage:true});
await page.evaluate(()=>document.documentElement.dataset.theme='light');
await page.setViewportSize({width:390,height:844});
await page.screenshot({path:`${folder}/mobile.png`,fullPage:true});
const mobile=[];
for(const [name,file] of routes){
 await page.getByRole('button',{name:'Open navigation',exact:true}).click();
 await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true}).click();
 await page.waitForTimeout(250);
 mobile.push({route:file,viewport:390,documentWidth:await page.evaluate(()=>document.documentElement.scrollWidth)});
}
await context.close();
const publicContext=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
await publicContext.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
await publicContext.route('**/api/session',route=>route.fulfill({json:{authenticated:false}}));
const publicPage=await publicContext.newPage();
for(const [hash,file] of [['','landing'],['#login','login']]){
 await publicPage.goto('http://127.0.0.1:5173/'+hash,{waitUntil:'domcontentloaded'});
 await publicPage.waitForTimeout(1000);await publicPage.screenshot({path:`${folder}/${file}.png`,fullPage:true});
}
await browser.close();
await writeFile(`${folder}/quality.json`,JSON.stringify({errors,mobile},null,2));
console.log(`Screenshots saved to ${folder}`);
console.log(JSON.stringify({errors,mobile}));
if(errors.length||mobile.some(item=>item.documentWidth>392))process.exitCode=1;
