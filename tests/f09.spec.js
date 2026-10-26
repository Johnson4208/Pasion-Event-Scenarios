import {test,expect} from '@playwright/test';

test('F09 country scopes retain navigation and separate reviewed coverage from samples',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F09',email:'f09@example.com'}}}));
 await page.route('**/api/research/macro?*',r=>{const scope=new URL(r.request().url()).searchParams.get('scope');return r.fulfill({json:{version:1,scope,status:'UNAVAILABLE',origin:'2026-10-12T00:00:00Z',series:[],coverage:{covered:[],missing:['cpi','policy_rate','labor','fx','growth']}}});});
 await page.goto('/');await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Macro Regime Monitor',exact:true}).click();
 const macro=page.locator('.macro-regime-page');
 await expect(macro).toContainText('No reviewed series registered for this scope');
 await expect(macro).not.toContainText('MODERATE GROWTH');
 await macro.getByRole('button',{name:'Choose your country',exact:true}).click();
 await macro.getByLabel('Choose country',{exact:true}).selectOption('japan');
 await expect(macro.getByRole('heading',{name:'Japan · Reviewed macro evidence'})).toBeVisible();
 await macro.getByLabel('Macro data mode').selectOption('sample');
 await expect(macro).toContainText('Illustrative generated charts');
 await expect(macro.getByRole('heading',{name:'Japan Overview'})).toBeVisible();
 await macro.getByLabel('Macro data mode').selectOption('reviewed');
 await expect(macro).not.toContainText('Nikkei 225');
});

test('F09 Company Research sends explicit commodity assumptions and shows a proposed bridge',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F09',email:'f09@example.com'}}}));
 const x={id:'mapping',segment:'Manufacturing',commodity:'Copper',grade:'Grade A',location:'Japan',period_start:'2027-01-01',period_end:'2027-12-31',currency:'USD',volume_unit:'tonne',output_volume:'100',input_volume:'80',output_repricing_fraction:'.5',input_repricing_fraction:'1',contract_reset:'Annual review',inventory_lag:'One month',hedge_scope:'None',fact_ids:['filing-fact'],known_at:'2026-10-12T00:00:00Z',expires_at:'2026-12-01T00:00:00Z'};
 await page.route('**/api/research/commodity-exposures?*',r=>r.fulfill({json:{version:1,exposures:[x]}}));
 let submitted;
 await page.route('**/api/research/commodity-stress',r=>{submitted=r.request().postDataJSON();return r.fulfill({json:{version:1,status:'SCENARIO',delta_ebit:'-250',currency:'USD',bridge:{output_effect:'500',input_effect:'-800',pass_through:'100',hedge_pnl:'-20',incremental_costs:'-30'},exposure:x}});});
 await page.goto('/');await page.getByRole('button',{name:'Expand company overview'}).click();
 const panel=page.getByRole('dialog').locator('.macro-evidence');
 await expect(panel).toContainText('filing-fact');
 await panel.getByLabel('output price delta (USD/tonne)').fill('10');await panel.getByLabel('input price delta (USD/tonne)').fill('10');
 await panel.getByLabel('pass through (USD)').fill('100');await panel.getByLabel('hedge pnl (USD)').fill('-20');await panel.getByLabel('incremental costs (USD)').fill('30');
 await panel.getByRole('button',{name:'Calculate proposed EBIT scenario'}).click();
 await expect(panel).toContainText('SCENARIO · Δ EBIT -250 USD');
 await expect(panel).toContainText('Review operating forecast drivers');
 expect(submitted.exposure_id).toBe('mapping');expect(submitted.output_price_delta).toBe('10');expect(submitted.currency).toBe('USD');
});
