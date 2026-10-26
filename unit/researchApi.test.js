import test from 'node:test';
import assert from 'node:assert/strict';
import {feasibilityView,metricText,bindCompanyIndicators} from '../src/researchApi.js';

const ready={version:1,status:'READY',quantity:100,lot:100,currency:'VND',expires_at:'2026-10-14T12:00:00Z',riskBudget:'0',maxLoss:'10',potentialProfit:'20',positionValue:'1000',ratio:'2'};
const clock=Date.parse('2026-10-14T11:00:00Z');
test('existing indicator rows preserve zero and withhold unsupported meanings',()=>{
 const rows=bindCompanyIndicators([{name:'Existing',rows:[{label:'Net revenue',value:'sample'},{label:'Gross revenue',value:'sample'},{label:'Return on equity',value:'sample'}]}],{metrics:{revenue:{status:'READY',origin:'ACTUAL',value:'0',unit:'currency',currency:'USD',source_ids:['fact-zero']},roe:{status:'WITHHELD',value:'20',unit:'percent',reason_codes:['OPENING_EQUITY_REQUIRED']}}})[0].rows;
 assert.equal(rows[0].value,'0 USD');assert.deepEqual(rows[0].source_ids,['fact-zero']);
 assert.notEqual(rows[1].value,'0 USD');assert.notEqual(rows[1].value,'sample');
 assert.notEqual(rows[2].value,'20 percent');assert.equal(rows[2].note,'OPENING_EQUITY_REQUIRED');
 assert.equal(rows[0].peer,'Unavailable');
});
test('metric display requires explicit ready status and units',()=>{
 assert.equal(metricText({status:'READY',value:'0',unit:'currency',currency:'VND'}),'0 VND');
 for(const metric of [{status:'WITHHELD',value:'5',unit:'percent'}, {status:'READY',value:null,unit:'percent'},
   {status:'READY',value:'Infinity',unit:'percent'}, {status:'READY',value:'5',unit:'currency'}]) assert.equal(metricText(metric),'—');
});
test('explicit status suppresses values and valid numeric zero survives',()=>{
 assert.equal(feasibilityView({...ready,status:'WITHHELD'},clock).shares,null);
 assert.equal(feasibilityView(ready,clock).riskBudget,0);
 assert.equal(feasibilityView(ready,clock).amount_currency,'VND');
});
test('invalid expiry, amount, currency and quantity cannot render as ready',()=>{
 for(const change of [{expires_at:'bad'},{maxLoss:null},{ratio:'NaN'},{currency:''},{quantity:101},{quantity:Infinity}]){
  const result=feasibilityView({...ready,...change},clock);assert.equal(result.status,'UNAVAILABLE');assert.equal(result.shares,null);
 }
 assert.equal(feasibilityView(ready,clock+3600000).status,'STALE');
});
