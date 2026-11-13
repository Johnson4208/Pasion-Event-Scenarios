import {test,expect} from '@playwright/test';

const empty={version:1,status:'UNAVAILABLE',company:{name:'Test company'},metrics:{},series:{},summary:[]};
const money=(value,currency='VND')=>({status:'READY',value,unit:'currency',currency});
function snapshot(ticker='AAPL',market='US',value='123456789',extra={}){
 const provider=market==='VN'?'CafeF':'SEC';
 return {version:1,ticker,market,issuer:ticker==='FPT'?'Công ty Cổ phần FPT':ticker,provider,period:'FY',period_end:'2025',cache_status:'LIVE',retrieved_at:'2026-11-13T00:00:00Z',source_url:market==='VN'?'https://cafef.vn/du-lieu/':'https://www.sec.gov/',financials:{...empty,status:'READY',metrics:{revenue:{...money(value,market==='VN'?'VND':'USD'),period_label:'FY 2025',provider,source_url:'https://cafef.vn/du-lieu/'},net_margin:{status:'READY',value:'16.0204',unit:'%',period_label:'FY 2025',provider},ebitda_margin:{status:'UNAVAILABLE',reason_codes:['EBITDA_EXPENSE_RECONCILIATION_REQUIRED']},free_cash_flow:{status:'UNAVAILABLE',reason_codes:['CASH_FLOW_RECONCILIATION_REQUIRED']}}},...extra};
}
test.beforeEach(async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:true,user:{name:'Source Tester',email:'test@example.com'}}}));
 await page.route('**/api/research/company/**',r=>r.fulfill({json:empty}));
 await page.route('**/api/research/valuation',r=>r.fulfill({json:{version:1,status:'WITHHELD',methods:[]}}));
 await page.route('**/api/research/financial-sources',r=>r.fulfill({json:{version:1,can_configure:true,sec_configured:false,configuration_origin:'none',sources:[]}}));
 await page.route('**/api/research/financials/**',r=>{const u=new URL(r.request().url());const ticker=u.pathname.split('/').pop();const market=u.searchParams.get('market');return r.fulfill({json:snapshot(ticker,market,ticker==='FPT'?'70112825100710':ticker==='HPG'?'156116094618482':'123456789')});});
});

test('company selection automatically fills the actual table without a source picker',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/#investment-research');
 await expect(page.locator('.ir-financial-table')).toContainText('123,456,789 USD');
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).fill('FPT');
 await page.locator('.ir-search-results button').filter({hasText:'FPT'}).click();
 const table=page.locator('.ir-financial-table');
 await expect(table).toContainText('70,112,825,100,710 VND');
 await expect(table).toContainText('FY 2025');
 await expect(table).toContainText('16.02 %');
 await expect(table).not.toContainText('123,456,789');
 await expect(page.locator('.financial-sources')).toContainText('CafeF');
 await expect(page.locator('.financial-sources select')).toHaveCount(0);
 await expect(page.locator('.financial-sources details')).not.toHaveAttribute('open','');
 await expect(table).toContainText('does not provide reconciled EBITDA');
 await expect(table).toContainText('Capital expenditure does not reconcile');
 await page.locator('.ir-bottom-grid').screenshot({path:'artifacts/automatic-financials-desktop.png'});
 expect(errors).toEqual([]);
});

test('top search Enter also changes the company and loads new figures',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/#investment-research');
 const search=page.getByRole('textbox',{name:'Search companies',exact:true});
 await search.fill('HPG');await search.press('Enter');
 await expect(page.locator('.ir-company-tags')).toContainText('HPG');
 await expect(page.locator('.ir-financial-table')).toContainText('156,116,094,618,482 VND');
 await expect(page.getByRole('combobox',{name:'Company market',exact:true})).toHaveValue('VN');
 expect(errors).toEqual([]);
});

test('submitting a known Vietnamese ticker infers its market',async({page})=>{
 await page.goto('/#investment-research');
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).fill('FPT');
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).press('Enter');
 await expect(page.locator('.ir-company-tags')).toContainText('FPT');
 await expect(page.locator('.ir-financial-table')).toContainText('70,112,825,100,710 VND');
});

test('reviewed values take precedence per metric while missing values fill from provider',async({page})=>{
 await page.route('**/api/research/company/**',r=>r.fulfill({json:{...empty,status:'READY',metrics:{revenue:{...money('42','USD'),period_type:'TTM'}}}}));
 await page.goto('/#investment-research');
 const table=page.locator('.ir-financial-table');
 await expect(table).toContainText('42 USD');
 await expect(table).toContainText('TTM');
 await expect(table).toContainText('16.02 %');
 await expect(table).not.toContainText('123,456,789');
});

test('stale public data is excluded',async({page})=>{
 await page.route('**/api/research/financials/**',r=>r.fulfill({json:snapshot('AAPL','US','123456789',{cache_status:'STALE'})}));
 await page.goto('/#investment-research');
 await expect(page.locator('.financial-sources')).toContainText('saved copy is stale');
 await expect(page.locator('.ir-financial-table')).not.toContainText('123,456,789');
});

test('failed new company request never leaves previous company figures',async({page})=>{
 await page.goto('/#investment-research');
 await expect(page.locator('.ir-financial-table')).toContainText('123,456,789');
 await page.route('**/api/research/financials/FPT?*',r=>r.fulfill({status:422,json:{reason_code:'PROVIDER_UNAVAILABLE'}}));
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).fill('FPT');
 await page.locator('.ir-search-results button').filter({hasText:'FPT'}).click();
 await expect(page.locator('.financial-sources')).toContainText('temporarily unavailable');
 await expect(page.locator('.ir-financial-table')).not.toContainText('123,456,789');
});

test('late response from old company cannot overwrite new selection',async({page})=>{
 let release,arrived;const pending=new Promise(resolve=>release=resolve);const requested=new Promise(resolve=>arrived=resolve);
 await page.route('**/api/research/financials/AAPL?*',async r=>{arrived();await pending;try{await r.fulfill({json:snapshot()});}catch{}});
 await page.goto('/#investment-research');await requested;
 await page.getByRole('textbox',{name:'Search companies',exact:true}).fill('FPT');
 await page.getByRole('textbox',{name:'Search companies',exact:true}).press('Enter');
 await expect(page.locator('.ir-financial-table')).toContainText('70,112,825,100,710 VND');
 release();
 await expect(page.locator('.ir-company-tags')).toContainText('FPT');
 await expect(page.locator('.ir-financial-table')).not.toContainText('123,456,789');
});

test('missing SEC contact has no historical fallback and saving retries automatically',async({page})=>{
 let configured=false,posted;
 await page.route('**/api/research/financials/**',r=>configured?r.fulfill({json:snapshot()}):r.fulfill({status:422,json:{reason_code:'SEC_USER_AGENT_NOT_CONFIGURED'}}));
 await page.route('**/api/admin/financial-sources',r=>{posted=r.request().postDataJSON();configured=true;return r.fulfill({json:{version:1,can_configure:true,sec_configured:true,configuration_origin:'local'}});});
 await page.goto('/#investment-research');
 const panel=page.locator('.financial-sources');
 await expect(panel).toContainText('contact email once');
 await expect(page.locator('.ir-financial-table')).not.toContainText('123,456,789');
 await panel.locator('summary').click();
 await panel.getByLabel('Contact email').fill('contact@example.com');
 await panel.getByRole('button',{name:'Save connection settings'}).click();
 await expect(page.locator('.ir-financial-table')).toContainText('123,456,789');
 expect(posted).toEqual({email:'contact@example.com'});
});

test('Vietnamese company search and data status fit a phone',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.addInitScript(()=>localStorage.setItem('pasion-preferences',JSON.stringify({language:'vi',theme:'light'})));
 await page.goto('/#investment-research');
 await page.getByRole('textbox',{name:'Tìm công ty để phân tích',exact:true}).fill('FPT');
 await page.locator('.ir-search-results button').filter({hasText:'FPT'}).click();
 await expect(page.locator('.financial-sources')).toContainText('Đã tự động tải số liệu');
 await expect(page.locator('.ir-financial-table')).toContainText('70.112.825.100.710 VND');
 for(const selector of ['.ir-company-search','.financial-sources'])expect(await page.locator(selector).evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
 await page.locator('.ir-company-search').screenshot({path:'artifacts/automatic-financials-mobile.png'});
});
