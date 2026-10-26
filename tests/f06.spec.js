import {test,expect} from '@playwright/test';

test('F06 defaults to evidence-gated diagnostics without fixed phases or quantities',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F06',email:'f06@example.com'}}}));
 await page.route('**/api/market/*/indicators',r=>r.fulfill({json:{version:1,ticker:new URL(r.request().url()).pathname.split('/')[3],status:'UNAVAILABLE',reason_codes:['NO_REVIEWED_OHLCV'],bars:[],events:[],indicators:{RVOL20:{status:'UNAVAILABLE',value:null,reason_codes:['PRIOR_20_SESSIONS_REQUIRED']}},phase:{status:'UNAVAILABLE',value:null,reason_codes:['NO_FORCED_PHASE_CLASSIFICATION']},trap_radar:{status:'UNAVAILABLE',probability:null,events:[]},trade_idea:{status:'WITHHELD',quantity:null,reason_codes:['SHARED_FEASIBILITY_REQUIRED']}}}));
 await page.goto('/');await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Indicators & VSA',exact:true}).click();
 const diagnostics=page.locator('.indicators-vsa-page');
 await expect(diagnostics).toContainText('NO_REVIEWED_OHLCV');
 await expect(diagnostics).not.toContainText('32.4%');
 await expect(diagnostics.locator('[role="meter"]')).toHaveCount(0);
 await expect(diagnostics).toContainText('SHARED_FEASIBILITY_REQUIRED');
 await expect(diagnostics.getByLabel('Chart sessions')).toHaveValue('60');
 await diagnostics.getByLabel('Chart sessions').selectOption('120');
 await expect(diagnostics.getByLabel('Chart sessions')).toHaveValue('120');
});
