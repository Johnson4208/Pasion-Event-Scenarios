import {test,expect} from '@playwright/test';

const financials={version:1,status:'UNAVAILABLE',company:{name:'Apple Inc.'},metrics:{},series:{},summary:[]};
function sec(stale=false){return {version:1,ticker:'AAPL',issuer:'Apple Inc.',period_end:'2025-09-27',source_status:'SEC_MACHINE_XBRL_NOT_HUMAN_REVIEWED',cache_status:stale?'STALE':'FRESH',retrieved_at:'2026-11-13T00:00:00Z',filing_url:'https://www.sec.gov/',financials:{...financials,status:'READY',metrics:{revenue:{status:'READY',value:'123456789',unit:'currency',currency:'USD'}}}};}
test.beforeEach(async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:true,user:{name:'Source Tester',email:'test@example.com'}}}));
 await page.route('**/api/research/company/**',r=>r.fulfill({json:financials}));
 await page.route('**/api/research/valuation',r=>r.fulfill({json:{version:1,status:'WITHHELD',methods:[]}}));
 await page.route('**/api/research/financial-sources',r=>r.fulfill({json:{version:1,can_configure:true,sec_configured:false,configuration_origin:'none',sources:[{id:'ssc',market:'VN',url:'https://congbothongtin.ssc.gov.vn/'}]}}));
 await page.route('**/api/research/sec/**',r=>r.fulfill({json:sec()}));
});
test('annual SEC labels, source switch and administrator contact configuration',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/#investment-research');
 const panel=page.getByRole('region',{name:'Financial data sources'});
 await expect(panel).toBeVisible();
 await expect(page.locator('.ir-financial-table')).toContainText('Revenue (FY)');
 await expect(page.locator('.ir-financial-table')).toContainText('123456789 USD');
 await panel.getByText('Configure SEC contact',{exact:true}).click();
 await panel.getByLabel('Contact email').fill('contact@example.com');
 let posted;
 await page.route('**/api/admin/financial-sources',r=>{posted=r.request().postDataJSON();return r.fulfill({json:{version:1,can_configure:true,sec_configured:true,configuration_origin:'local',sources:[]}});});
 await panel.getByRole('button',{name:'Save connection settings'}).click();
 await expect(panel).toContainText('Contact saved');expect(posted).toEqual({email:'contact@example.com'});
 await panel.getByRole('combobox').selectOption('VN');
 await expect(panel).toContainText('Upload the original statement');
 await expect(page.locator('.ir-financial-table')).not.toContainText('123456789 USD');
 expect(errors).toEqual([]);
});
test('stale SEC cache is excluded from financial indicators',async({page})=>{
 await page.route('**/api/research/sec/**',r=>r.fulfill({json:sec(true)}));
 await page.goto('/#investment-research');
 await expect(page.locator('.financial-sources')).toContainText('Cached copy is stale');
 await expect(page.locator('.ir-financial-table')).not.toContainText('123456789 USD');
});
test('Vietnamese source controls fit a phone viewport',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.addInitScript(()=>localStorage.setItem('pasion-preferences',JSON.stringify({language:'vi',theme:'light'})));
 await page.goto('/#investment-research');
 const panel=page.locator('.financial-sources');await expect(panel).toContainText('Nguồn dữ liệu tài chính');
 await panel.scrollIntoViewIfNeeded();
 expect(await panel.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
 await panel.screenshot({path:'artifacts/financial-sources-mobile.png'});
});
