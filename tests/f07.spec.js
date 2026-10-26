import {test,expect} from '@playwright/test';

test('F07 missing account withholds quantity but keeps local draft saving',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F07',email:'f07@example.com'}}}));
 await page.route('**/api/trades/feasibility',r=>r.fulfill({json:{version:1,status:'WITHHELD',quantity:null,shares:null,reason_codes:['ACCOUNT_BASELINE_REQUIRED'],scenarios:[]}}));
 await page.goto('/');await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Trade Planner',exact:true}).click();
 await expect(page.getByRole('button',{name:/Kelly Criterion/})).toBeDisabled();
 await expect(page.locator('.trade-planner-page')).toContainText('ACCOUNT_BASELINE_REQUIRED');
 await page.getByRole('button',{name:'Save trade plan',exact:true}).click();
 await expect(page.locator('.tp-plans-table')).toContainText('Recheck draft');
 await expect(page.locator('.trade-planner-page')).not.toContainText('39.8%');
});
