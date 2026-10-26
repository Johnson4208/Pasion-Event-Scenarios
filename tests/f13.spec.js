import {test,expect} from '@playwright/test';
test('F13 watch import requires explicit consent and alert evaluation reports missing quotes',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F13',email:'f13@example.com'}}}));
 await page.route('**/api/research/watch',r=>r.fulfill({json:{version:1,intents:[],events:[],acknowledgments:[]}}));
 await page.route('**/api/research/watch/evaluate',r=>r.fulfill({json:{version:1,created:[]}}));
 await page.goto('/');await page.getByText('Private watch & alert event log',{exact:true}).click();
 await expect(page.getByRole('button',{name:'Import browser watchlist'})).toBeDisabled();
 await page.getByRole('checkbox',{name:"I consent to importing this browser's watchlist as unverified watch intents"}).check();
 await expect(page.getByRole('button',{name:'Import browser watchlist'})).toBeEnabled();
 await page.getByRole('button',{name:'Evaluate verified alert sources'}).click();
 await expect(page.getByText('0 new immutable evaluations. Replay creates no duplicate notifications.')).toBeVisible();
});
