import {test} from 'node:test';
import assert from 'node:assert/strict';
import {chooseMetric,formatFinancial,usable} from '../src/automaticFinancials.js';
const valid={status:'READY',value:'0',unit:'currency',currency:'VND'};
test('zero is a valid financial value, missing and NaN are not',()=>{
 assert.equal(formatFinancial(valid),'0 VND');
 for(const value of [null,'',NaN,Infinity])assert.equal(usable({...valid,value}),false);
});
test('partial reviewed coverage does not block other provider metrics',()=>{
 const provider={financials:{metrics:{revenue:{...valid,value:'200'},net_income:{...valid,value:'10'}}}};
 const reviewed={metrics:{revenue:valid,net_income:{status:'UNAVAILABLE'}}};
 assert.equal(chooseMetric('revenue',reviewed,provider).value,'0');
 assert.equal(chooseMetric('net_income',reviewed,provider).value,'10');
 assert.equal(chooseMetric('net_income',reviewed,{...provider,cache_status:'STALE'}).status,'UNAVAILABLE');
});
