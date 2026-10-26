import {test,expect} from '@playwright/test';

test('F05 never substitutes fixed percentages or a confidence meter',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F05',email:'f05@example.com'}}}));
 await page.route('**/api/market/stock/FPT/analysis',r=>r.fulfill({json:{version:1,ticker:'FPT',horizons:[5,21,63,252].map(horizon_sessions=>({horizon_sessions,status:'UNCERTAIN',reason:'INSUFFICIENT_SAMPLE_OR_RELIABILITY',p_up:null,p_down:null,sample_count:20,features:{return_1:.01}}))}}));
 await page.goto('/');
 await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Stock Analytics',exact:true}).click();
 const forecast=page.locator('.stock-prediction-panel');
 await expect(forecast.locator('.stock-horizons button')).toHaveCount(4);
 await expect(forecast.locator('.stock-horizons strong')).toHaveText(['UNCERTAIN','UNCERTAIN','UNCERTAIN','UNCERTAIN']);
 await expect(forecast.locator('[role="meter"]')).toHaveCount(0);
 await expect(forecast).not.toContainText('55.8%');
 await forecast.getByRole('button',{name:/12 months/}).click();
 await expect(forecast.getByRole('button',{name:/12 months/})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByLabel('Financial data mode')).toHaveValue('reviewed');
});

test('F05 displays only reliable complementary probabilities and expires them',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F05',email:'f05@example.com'}}}));
 await page.route('**/api/market/stock/FPT/analysis',r=>r.fulfill({json:{version:1,ticker:'FPT',horizons:[{horizon_sessions:21,status:'READY',p_up:.7,p_down:.3,brier_skill:.1,sample_count:100,calibration_error:.02,last_valid_origin:new Date().toISOString(),prediction_expires_at:new Date(Date.now()+2500).toISOString(),model_expires_at:new Date(Date.now()+60000).toISOString(),features:{}}]}}));
 await page.goto('/');await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Stock Analytics',exact:true}).click();
 const forecast=page.locator('.stock-prediction-panel');
 await expect(forecast.locator('.stock-prediction-stats article').first()).toContainText('70.0%');
 await expect(forecast.locator('.stock-prediction-stats article').first().locator('strong')).toHaveText('—',{timeout:6000});
});
