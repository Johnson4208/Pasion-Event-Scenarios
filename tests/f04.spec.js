import {test,expect} from '@playwright/test';
test('F04 original model cards show eligible calculations without a replacement page',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F04',email:'f04@example.test'}}}));
 await page.route('**/api/research/company/*',r=>r.fulfill({json:{version:1,metrics:{revenue:{status:'READY',value:'0',unit:'currency',currency:'VND',source_ids:['fact-zero']}}}}));
 await page.route('**/api/research/valuation',r=>r.fulfill({json:{version:1,run_id:'existing-card-run',calculation_version:'f04-v1',quote_gap:{status:'UNAVAILABLE'},methods:[{method:'FCFF',status:'READY',value:'123400',currency:'VND',source_ids:['fact-zero'],reason_codes:[]},...['P/E','DDM','Gordon','Asset-based'].map(method=>({method,status:'WITHHELD',value:null,reason_codes:['UNVERIFIED_ASSUMPTIONS'],source_ids:[]}))]}}));
 await page.goto('/#investment-research',{waitUntil:'domcontentloaded'});
 const research=page.locator('.investment-research');
 await expect(research.locator('.ir-model-card')).toHaveCount(5);
 await expect(research.locator('.ir-model-card').first()).toContainText('123,400');
 await expect(research.locator('.ir-financial-table')).toContainText('0 VND');
 await expect(research.locator('.ir-chart-bar-target')).toHaveCount(1);
 await expect(page.getByRole('button',{name:'Run eligibility and valuation'})).toHaveCount(0);
 await expect(page.getByRole('heading',{name:'Forecast scenario editor'})).toHaveCount(0);
 await expect(research).not.toContainText('67,800');
 await research.locator('.ir-model-card').first().getByRole('button',{name:/View details/}).click();
 await expect(page.getByRole('dialog')).toContainText('fact-zero');
});
