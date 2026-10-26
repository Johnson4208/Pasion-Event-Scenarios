import {test,expect} from '@playwright/test';
test.beforeEach(async({page})=>{await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F03',email:'f03@example.test'}}}));});
test('F03 original company tables preserve zero and existing source details show lineage',async({page})=>{
 const fact={definition_id:'cfo',value:'0',unit:'currency',currency:'USD',scope:'consolidated',accounting_basis:'US_GAAP',origin:'ACTUAL',status:'READY',period_start:'2025-01-01',period_end:'2025-12-31',known_at:'2026-01-10T00:00:00Z',source_ids:['reviewed-1'],reason_codes:[]};
 await page.route('**/api/research/company/*',r=>r.fulfill({json:{version:1,company:{ticker:'AAPL',name:'Apple'},period:'TTM',status:'READY',metrics:{cfo:fact,revenue:{...fact,definition_id:'revenue'}},summary:[],series:{}}}));
 await page.route('**/api/research/facts/*/evidence',r=>r.fulfill({json:{...fact,id:'reviewed-1',revision:'revision-2',evidence:{page:7,table:'Cash-flow statement',tag:'CFO'}}}));
 await page.goto('/',{waitUntil:'domcontentloaded'});
 await expect(page.getByRole('region',{name:'Reviewed company financials'})).toHaveCount(0);
 await page.getByRole('button',{name:'Expand company overview'}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.locator('.research-indicator-grid')).toContainText('0 USD');
 await dialog.getByRole('tablist',{name:'Research sections'}).getByRole('tab',{name:'Cash flow',exact:true}).click();
 const row=dialog.locator('.research-metric-table tbody tr').filter({hasText:'Operating cash flow'});
 await expect(row).toContainText('0 USD');
 await row.getByRole('button').click();
 await expect(dialog.getByRole('region',{name:'Source details'})).toContainText('revision-2');
 await expect(dialog.getByRole('region',{name:'Source details'})).toContainText('Cash-flow statement');
});
test('F03 original comparison table marks incompatible values and suppresses relative bars',async({page})=>{
 await page.route('**/api/research/compare?*',r=>r.fulfill({json:{version:1,companies:[{ticker:'AAPL'},{ticker:'MSFT'},{ticker:'NVDA'}],rows:[{definition_id:'revenue',comparable:false,cells:[{value:'0',unit:'currency',currency:'USD',status:'READY'},{value:'100',unit:'currency',currency:'VND',status:'READY'},{value:null,status:'UNAVAILABLE'}]}]}}));
 await page.goto('/#compare-companies',{waitUntil:'domcontentloaded'});
 await expect(page.locator('.comparison-table')).toContainText('0 USD');
 await expect(page.locator('.comparison-table')).toContainText('not comparable');
 await expect(page.locator('.comparison-bars')).toContainText('Not comparable');
});
