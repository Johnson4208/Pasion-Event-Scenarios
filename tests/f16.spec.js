import {test,expect} from '@playwright/test';
test('F16 health remains a lean admin panel with isolated subsystem status',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:true,user:{name:'Admin',email:'admin@example.com'}}}));
 await page.route('**/api/admin/accounts',r=>r.fulfill({json:{accounts:[]}}));
 await page.route('**/api/admin/health',r=>r.fulfill({json:{version:1,status:'PARTIAL',run_id:'run',trace_id:'trace',release_gate:'REVIEW_REQUIRED',subsystems:[{subsystem:'provider',status:'UNAVAILABLE',reason_codes:['NO_FEED']},{subsystem:'financial_periods',status:'READY',reason_codes:[]}]}}));
 await page.goto('/#admin');await page.getByRole('navigation',{name:'Administration sections'}).getByRole('button',{name:'Operational health'}).click();
 await expect(page.locator('.admin-page')).toContainText('provider · UNAVAILABLE');await expect(page.locator('.admin-page')).toContainText('financial_periods · READY');await expect(page.locator('.admin-page')).toContainText('Trace trace');
});
