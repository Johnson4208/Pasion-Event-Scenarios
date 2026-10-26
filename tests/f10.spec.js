import {readFileSync} from 'node:fs';
import {test,expect} from '@playwright/test';

const base={category:'Geopolitics',factor:'Conflict risk',focus:'Vietnam',horizon:'30 days'};
function source(i=0,extra={}){return {id:'story-'+i,title:'Vietnam regional risk update '+i,url:'https://example.org/story-'+i,
 description:'Published regional evidence for a possible change',source:'Sample publisher',published_at:'2026-10-23T08:00:00Z',
 weight:.65,direction:-.8,direction_status:'DIRECTIONAL',geographic_relation:'DIRECT_SCOPE',...extra};}
function report(query=base,extras={}){
 const items=[source(1),source(2)];
 const rows=Array.from({length:10},(_,i)=>({
  id:'scenario-'+i,title:i===0?'Rapid deterioration':i===1?'Gradual improvement':'Scenario pathway '+(i+1),
  definition:'Conditional economic development '+(i+1),rank:i+1,
  qualifier_fit:'BOTH',status:i<3?'EXPERIMENTAL_ESTIMATE':'PENDING_EVIDENCE',supporting_source_count:i<3?2:0,
  sources:i<3?items:[],support_index:i<3?.6-i*.08:null,
  scenario_share_percent:i<3?[38.3,33.5,28.2][i]:0,
  scenario_share_status:i<3?'NORMALIZED_EXPERIMENTAL_UNCALIBRATED':'NOT_CALCULATED',
  experimental_probability:i<3?{status:'EXPERIMENTAL_UNCALIBRATED',model_version:'event-probability-experimental-v2',scenario_id:'scenario-'+i,assumed_prior:.5,evidence_cluster_count:2,probability_estimate:[.732,.641,.538][i],
    prior_sensitivity_range:[.31,.86],calibrated:false}:null
 }));
 return {version:1,status:'EVIDENCE_AVAILABLE',...query,generated_at:'2026-10-24T03:00:00Z',
  source_count:2,items,coverage:{requests:5,feed_successes:3},
  dynamic_scenarios:{ranked_scenarios:rows,scenario_distribution:{status:'NORMALIZED_EXPERIMENTAL_UNCALIBRATED',total_percent:100,estimated_scenario_count:3}},bayesian_forecast:{status:'UNAVAILABLE'},
  probability_status:'EXPERIMENTAL_UNCALIBRATED',...extras};
}
async function start(page){
 await page.goto('/#event-scenarios');
 await expect(page.getByRole('heading',{name:'Dynamic Scenario Forecasting'})).toBeVisible();
}
test.beforeEach(async({page})=>{
 await page.route('**/api/research/events/forecast',r=>r.fulfill({json:{version:1,...r.request().postDataJSON(),scenario_forecast:{status:'UNAVAILABLE',reason_code:'NO_MODEL_FOR_THIS_CONTEXT'},items:[]}}));
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'Event Tester',email:'event-test@example.com'}}}));
 await page.route('**/api/research/company/**',r=>r.fulfill({json:{status:'UNAVAILABLE'}}));
});
test('initial results remain compact without implying zero probability',async({page})=>{
 await start(page);
 await expect(page.locator('.events-ranking-compact')).toBeVisible();
 await expect(page.locator('.events-initial-summary')).toContainText('—');
 await expect(page.locator('.events-initial-summary')).toContainText('Not calculated');
 await expect(page.locator('.events-ranked-item')).toHaveCount(0);
});
test('restored probability ranking shows ten pathways and bounded research labels',async({page})=>{
 await page.route('**/api/research/events/live?*',r=>r.fulfill({json:report()}));
 await start(page);await page.getByRole('button',{name:/^Analyze/}).click();
 await expect(page.locator('.events-ranked-item')).toHaveCount(10);
 await expect(page.locator('.events-rank-value').first()).toHaveText('73.2%*');
 await expect(page.locator('.events-rank-value').nth(1)).toHaveText('64.1%*');
 await expect(page.locator('.events-ranked-note')).toContainText('not validated event probabilities');
 await expect(page.locator('.events-distribution-total')).toHaveCount(0);
 await page.getByRole('combobox',{name:'Display metric'}).selectOption('share');
 await expect(page.locator('.events-distribution-total')).toContainText('100.0%');
 const shares=await page.locator('.events-rank-value').allTextContents();
 expect(shares.reduce((total,share)=>total+(Number.parseFloat(share)||0),0)).toBeCloseTo(100,1);
 await expect(page.locator('.events-rank-value').nth(9)).toHaveText('—');
 await expect(page.locator('.events-ranked-note')).toContainText('Relative allocation');
 await expect(page.getByRole('heading',{name:'Ranked scenario pathways'})).toBeVisible();
});
test('one-sided news must not show a fake 100 percent outcome forecast',async({page})=>{
 const data=report(base,{
   scenario_presentation:{type:'UNAVAILABLE',status:'NOT_CALCULATED',rows:[],total_percent:null},
   dynamic_scenarios:{
     ranked_scenarios:Array.from({length:10},(_,i)=>({id:'scenario-'+i,rank:i+1,
       title:'Scenario '+i,scenario_share_percent:0,scenario_share_status:'NOT_CALCULATED',
       supporting_source_count:i===0?47:i===1?8:0,sources:[]})),
     scenario_distribution:{status:'WITHHELD_CONCENTRATED_EVIDENCE',
       reason_code:'ONLY_ONE_NET_SUPPORTED_PATHWAY',estimated_scenario_count:1,total_percent:null}
   }
 });
 await page.route('**/api/research/events/live?*',r=>r.fulfill({json:data}));
 await start(page);await page.getByRole('button',{name:/^Analyze/}).click();
 await expect(page.locator('.events-empty-diagnostic')).toContainText('Evidence leans strongly one way');
 await expect(page.locator('.events-ranked-item')).toHaveCount(10);
 await expect(page.locator('.events-rank-value')).toHaveCount(10);
 await expect(page.locator('.events-ranked-note')).toContainText('not ranked by probability');
 await expect(page.locator('.events-rank-value').first()).toHaveText('—');
 await expect(page.locator('.events-distribution-total')).toHaveCount(0);
 await expect(page.getByRole('button',{name:/Evidence/}).first()).toBeEnabled();
});
for (const filename of ['event-reference-forecast.json','event-seven-outcomes.json']) {
 test('complete historical family is visible: '+filename,async({page})=>{
  const model=JSON.parse(readFileSync(new URL('./fixtures/'+filename,import.meta.url)));
  await page.route('**/api/research/events/live?*',r=>r.fulfill({json:report(base,{scenario_forecast:model})}));
  await start(page);await page.getByRole('button',{name:/^Analyze/}).click();
  await expect(page.locator('.ev-comparison-row')).toHaveCount(model.scenarios.length);
  await expect(page.locator('.ev-outcome-probability').first()).toContainText('%');
  await expect(page.locator('.ev-outcome-range').first()).toContainText('%');
 });
}
test('series preparation restores five probabilities even when news fails',async({page})=>{
 const model=JSON.parse(readFileSync(new URL('./fixtures/event-series-forecast.json',import.meta.url)));
 await page.route('**/api/research/events/live?*',r=>r.fulfill({status:503,json:{message:'News unavailable'}}));
 await page.route('**/api/research/events/forecast',r=>r.fulfill({json:{version:1,...model.context,scenario_forecast:model,items:[],status:'FORECAST_AVAILABLE'}}));
 await start(page);
 await page.getByRole('combobox',{name:'Category',exact:true}).selectOption('Markets');
 await page.getByLabel('Region / entity').fill('United States');
 await page.getByRole('button',{name:/^Analyze/}).click();
 await expect(page.locator('.ev-comparison-row')).toHaveCount(5);
 await expect(page.locator('.events-error')).toContainText('News collection failed');
});
test('forged presentation without validated model cannot claim historical probabilities',async({page})=>{
 await page.route('**/api/research/events/live?*',r=>r.fulfill({json:report(base,{scenario_presentation:{type:'HISTORICAL_REFERENCE',status:'HISTORICAL_REFERENCE_ESTIMATE',rows:[{id:'fake',scenario_share_percent:100}]}})}));
 await start(page);await page.getByRole('button',{name:/^Analyze/}).click();
 await expect(page.locator('.ev-comparison-row')).toHaveCount(0);
 await expect(page.locator('.events-model-flag')).not.toContainText('Historical');
});
test('loading overlays the prior results and clears after evidence returns',async({page})=>{
 let release;let count=0;
 await page.route('**/api/research/events/live?*',async r=>{
   count++;
   if(count===1)return r.fulfill({json:report()});
   await new Promise(resolve=>{release=resolve});
   await r.fulfill({json:report()});
 });
 await start(page);await page.getByRole('button',{name:/^Analyze/}).click();
 await expect(page.locator('.events-rank-value').first()).toHaveText('73.2%*');
 await page.getByRole('button',{name:/^Analyze/}).click();
 await expect(page.locator('.events-loading-spinner')).toBeVisible();
 await expect(page.locator('.events-ranking-shell')).toHaveAttribute('aria-busy','true');
 release();
 await expect(page.locator('.events-loading-spinner')).toHaveCount(0);
 await expect(page.locator('.events-rank-value').first()).toHaveText('73.2%*');
});
test('evidence opens as overlay rather than a long visible article list',async({page})=>{
 await page.route('**/api/research/events/live?*',r=>r.fulfill({json:report()}));
 await start(page);await page.getByRole('button',{name:/^Analyze/}).click();
 await page.locator('.events-ranked-item').first().getByRole('button',{name:/Evidence/}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog).toBeVisible();
 await expect(dialog.getByRole('link')).toHaveCount(2);
 await expect(dialog).toContainText('Sample publisher');
 await page.keyboard.press('Escape');
 await expect(dialog).toHaveCount(0);
});
test('horizons separate the five short and three long choices',async({page})=>{
 await start(page);
 let select=page.getByRole('combobox',{name:'Forecast duration'});
 await expect(select.locator('option')).toHaveCount(5);
 await page.getByRole('button',{name:'Long-term'}).click();
 select=page.getByRole('combobox',{name:'Forecast duration'});
 await expect(select.locator('option')).toHaveCount(3);
 await expect(select).toHaveValue('180 days');
 await page.getByRole('button',{name:'Short-term'}).click();
 await expect(select).toHaveValue('30 days');
});
test('empty or externally scoped evidence does not invent probabilities',async({page})=>{
 await page.route('**/api/research/events/live?*',r=>r.fulfill({json:report(base,{status:'UNAVAILABLE',
  source_count:1,items:[source(1,{geographic_relation:'EXTERNAL_CONTEXT'})]})}));
 await start(page);await page.getByRole('button',{name:/^Analyze/}).click();
 await expect(page.locator('.events-empty-diagnostic')).toBeVisible();
 await expect(page.locator('.events-ranked-item')).toHaveCount(10);
 await expect(page.locator('.events-ranked-item').first().getByRole('button',{name:/Evidence/})).toBeVisible();
 await expect(page.locator('.events-rank-value').first()).toHaveText('—');
});
test('research is saved separately from server event memory',async({page})=>{
 await page.route('**/api/research/events/live?*',r=>r.fulfill({json:report()}));
 await start(page);await page.getByRole('button',{name:/^Analyze/}).click();
 await page.getByRole('button',{name:'Save research'}).click();
 await expect(page.locator('.events-history-item')).toHaveCount(1);
 const entry=await page.evaluate(()=>{
   const key=Object.keys(localStorage).find(k=>k.endsWith('-event-research'));
   return key?JSON.parse(localStorage.getItem(key))[0]:null;
 });
 expect(entry).toBeTruthy();
 expect(entry.factor).toBe('Conflict risk');
 expect(entry.research.dynamic_scenarios.ranked_scenarios).toHaveLength(10);
});
test('mobile ranking and evidence modal remain inside screen width',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.route('**/api/research/events/live?*',r=>r.fulfill({json:report()}));
 await start(page);await page.getByRole('button',{name:/^Analyze/}).click();
 await expect(page.locator('.events-ranked-item')).toHaveCount(10);
 await page.locator('.events-ranked-item').first().getByRole('button',{name:/Evidence/}).click();
 await expect(page.getByRole('dialog')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
});

test('controls cannot relabel an in-flight response',async({page})=>{
 let release;
 await page.route('**/api/research/events/live?*',async r=>{await new Promise(resolve=>{release=resolve});await r.fulfill({json:report()});});
 await start(page);await page.getByRole('button',{name:/^Analyze/}).click();
 await expect(page.getByRole('combobox',{name:'Category',exact:true})).toBeDisabled();
 await expect(page.getByLabel('Region / entity')).toBeDisabled();
 release();await expect(page.locator('.events-rank-value').first()).toHaveText('73.2%*');
 await page.getByLabel('Region / entity').fill('World');
 await expect(page.locator('.events-ranked-item')).toHaveCount(0);
});

test('occurrence probabilities remain independent and saved reports can be reopened',async({page})=>{
 const model=JSON.parse(readFileSync(new URL('./fixtures/event-occurrence-forecast.json',import.meta.url)));
 await page.route('**/api/research/events/live?*',r=>r.fulfill({json:report(model.context,{scenario_forecast:model})}));
 await start(page);
 await page.getByLabel('Probability question').selectOption('OCCURRENCE');
 await page.getByRole('button',{name:/^Analyze/}).click();
 await expect(page.locator('.ev-comparison-row')).toHaveCount(model.scenarios.length);
 await expect(page.locator('.ev-comparison')).toContainText('do not need to add up to 100%');
 await page.getByRole('button',{name:'Save research'}).click();
 await page.getByLabel('Region / entity').fill('World');
 await page.getByRole('button',{name:'Open report'}).click();
 await expect(page.getByLabel('Region / entity')).toHaveValue(model.context.focus);
 await expect(page.locator('.ev-comparison-row')).toHaveCount(model.scenarios.length);
});
test('mobile historical estimates and uncertainty stay visible without overflow',async({page})=>{
 const model=JSON.parse(readFileSync(new URL('./fixtures/event-reference-forecast.json',import.meta.url)));
 await page.setViewportSize({width:390,height:844});
 await page.route('**/api/research/events/live?*',r=>r.fulfill({json:report(base,{scenario_forecast:model})}));
 await start(page);await page.getByRole('button',{name:/^Analyze/}).click();
 await expect(page.locator('.ev-comparison-row')).toHaveCount(3);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
});
test('translated category labels retain stable API identifiers',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('pasion-preferences',JSON.stringify({language:'vi',theme:'light'})));
 await start(page);
 await page.getByRole('combobox',{name:'Category',exact:true}).selectOption('Economy');
 await expect(page.getByRole('combobox',{name:'Factor',exact:true})).toHaveValue('Inflation');
});
