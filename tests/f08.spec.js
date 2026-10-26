import {test,expect} from '@playwright/test';
test('F08 original portfolio preserves zero cash and unknown lot valuation',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F08',email:'f08@example.test'}}}));
 const state={currency:'USD',cash:'0',reserved_cash:'0',as_of:'2026-10-14T12:00:00Z',source:'MANUAL_CONFIRMED',lots:[{id:'lot-a',ticker:'AAPL',quantity:'2',unit_cost:'10',currency:'USD',sector:'Technology'}],targets:[],watchlist:[]};
 let saved=null;
 await page.route('**/api/portfolio/snapshot',async r=>{
  if(r.request().method()==='POST'){saved=r.request().postDataJSON();await r.fulfill({json:{version:1}});return;}
  await r.fulfill({json:{version:1,revision:1,state:saved?{...state,lots:[]}:state,status:'PARTIAL',currency:'USD',known_holdings_value:'0',total_value:null,unrealized_pnl:null,available_budget:{cash_after_entered_reserves:'0'},coverage:{priced_lots:0,total_lots:1},lots:saved?[]:[{...state.lots[0],cost_basis:'20',market_value:null,unrealized_pnl:null,mark:null,reason_codes:['QUOTE_REQUIRED']}],performance:{status:'UNAVAILABLE'}}});
 });
 await page.goto('/#portfolio-risk',{waitUntil:'domcontentloaded'});
 const portfolio=page.locator('.portfolio-monitor-v2');
 await expect(portfolio.locator('.portfolio-overview-stats')).toContainText('0 USD');
 await expect(portfolio.locator('.portfolio-table-vnd')).toContainText('AAPL');
 await expect(portfolio.locator('.portfolio-market-value')).toHaveText('Unavailable');
 await expect(portfolio.locator('.portfolio-main-line')).toHaveAttribute('d','');
 await expect(page.getByRole('heading',{name:'Manual account observations'})).toHaveCount(0);
 await portfolio.getByRole('button',{name:'Remove AAPL',exact:true}).click();
 await expect.poll(()=>saved?.expected_revision).toBe(1);
 expect(saved.cash).toBe('0');expect(saved.lots).toEqual([]);
});
