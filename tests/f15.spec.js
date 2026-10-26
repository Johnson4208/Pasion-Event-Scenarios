import {test,expect} from '@playwright/test';
test('F15 shadow Distribution is isolated in administration and explains withheld allocations',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:true,user:{name:'Admin',email:'admin@example.com'}}}));
 await page.route('**/api/admin/accounts',r=>r.fulfill({json:{accounts:[]}}));
 await page.route('**/api/admin/distribution',r=>r.fulfill({json:{version:1,status:'SHADOW_ONLY_NO_ALLOCATION',pools:[],candidates:[],events:[]}}));
 await page.goto('/#admin');await page.getByRole('navigation',{name:'Administration sections'}).getByRole('button',{name:'Shadow Distribution'}).click();
 await expect(page.locator('.admin-page')).toContainText('simulated review slots');await expect(page.locator('.admin-page')).toContainText('Candidate quantities remain withheld');
});
