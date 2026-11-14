import {test} from 'node:test';
import assert from 'node:assert/strict';
import {calculateValuation as calc} from '../src/valuationCalculators.js';

test('P/E, Gordon and adjusted asset values use explicit inputs',()=>{
 assert.equal(calc('P/E',{eps:5,multiple:12}).value,60);
 assert.ok(Math.abs(calc('Gordon',{nextDividend:3,discount:10,terminal:4}).value-50)<1e-9);
 assert.equal(calc('Asset-based',{equity:1000,adjustments:-200,shares:20}).value,40);
});
test('flat perpetual cash flows agree with analytical values',()=>{
 const dcf=calc('DCF',{fcff:100,growth:0,discount:10,terminal:0,cash:50,nonOperating:20,debt:200,minority:10,shares:10});
 assert.ok(Math.abs(dcf.enterprise-1000)<1e-9);
 assert.ok(Math.abs(dcf.value-86)<1e-9);
 assert.ok(Math.abs(calc('DDM',{dividend:3,growth:0,discount:10,terminal:0}).value-30)<1e-9);
 assert.equal(dcf.cashflows.length,5);assert.equal(dcf.status,'USER_SCENARIO');
});
test('missing, impossible and nonfinite assumptions never create a value',()=>{
 assert.throws(()=>calc('P/E',{eps:'',multiple:10}),/MISSING/);
 assert.throws(()=>calc('P/E',{eps:-2,multiple:10}),/POSITIVE/);
 assert.throws(()=>calc('Gordon',{nextDividend:3,discount:5,terminal:5}),/DISCOUNT/);
 assert.throws(()=>calc('Asset-based',{equity:100,adjustments:0,shares:0}),/POSITIVE/);
 assert.throws(()=>calc('P/E',{eps:Infinity,multiple:10}),/MISSING/);
});
