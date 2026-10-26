import {test,expect} from '@playwright/test';
test('F14 reviewed assistant exposes missing data without fabricated sample numbers',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F14',email:'f14@example.com'}}}));
 await page.route('**/api/research/assistant',r=>r.fulfill({json:{version:1,status:'UNAVAILABLE',answer:'Reviewed revenue is unavailable.',citations:[]}}));
 await page.goto('/');await page.getByRole('navigation',{name:'Account navigation'}).getByRole('button',{name:'Assistant',exact:true}).click();
 await page.getByLabel('Ask a finance question').fill('What is revenue?');await page.getByRole('button',{name:'Ask reviewed assistant'}).click();
 await expect(page.locator('.assistant-conversation')).toContainText('UNAVAILABLE');await expect(page.locator('.assistant-main')).not.toContainText('64%');
});
