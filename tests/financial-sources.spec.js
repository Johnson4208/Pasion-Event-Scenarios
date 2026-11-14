import {test,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
const realFpt=JSON.parse(execFileSync('python',['-c',`import sys,json;from pathlib import Path;sys.path.insert(0,'backend');import public_financials as p;f=Path('backend/fixtures/public_financials');d=lambda n:json.loads((f/('fpt-'+n+'.json')).read_text(encoding='utf-8'));print(json.dumps(p.normalize('FPT',d('summary'),d('balance'),d('cash'),d('income'))))`],{encoding:'utf8'}));

const empty={version:1,status:'UNAVAILABLE',company:{name:'Test company'},metrics:{},series:{},summary:[]};
const money=(value,currency='VND')=>({status:'READY',value,unit:'currency',currency});
function snapshot(ticker='AAPL',market='US',value='123456789',extra={}){
 if(ticker==='FPT'&&market==='VN')return {...realFpt,cache_status:'LIVE',retrieved_at:'2026-11-14T00:00:00Z',...extra};
 const provider=market==='VN'?'CafeF':'SEC';
 return {version:1,ticker,market,issuer:ticker==='FPT'?'Công ty Cổ phần FPT':ticker,provider,period:'FY',period_end:'2025',cache_status:'LIVE',retrieved_at:'2026-11-13T00:00:00Z',source_url:market==='VN'?'https://cafef.vn/du-lieu/':'https://www.sec.gov/',financials:{...empty,status:'READY',metrics:{revenue:{...money(value,market==='VN'?'VND':'USD'),period_label:'FY 2025',provider,source_url:'https://cafef.vn/du-lieu/'},net_margin:{status:'READY',value:'16.0204',unit:'%',period_label:'FY 2025',provider},ebitda_margin:{status:'UNAVAILABLE',reason_codes:['EBITDA_EXPENSE_RECONCILIATION_REQUIRED']},free_cash_flow:{status:'UNAVAILABLE',reason_codes:['CASH_FLOW_RECONCILIATION_REQUIRED']}}},...extra};
}
test.beforeEach(async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:true,user:{name:'Source Tester',email:'test@example.com'}}}));
 await page.route('**/api/research/company/**',r=>r.fulfill({json:empty}));
 await page.route('**/api/research/reports/**',r=>{const u=new URL(r.request().url());return r.fulfill({json:{version:1,ticker:u.pathname.split('/').pop(),market:u.searchParams.get('market'),reports:[],warnings:[]}});});
 await page.route('**/api/research/valuation',r=>r.fulfill({json:{version:1,status:'WITHHELD',methods:[]}}));
 await page.route('**/api/research/financial-sources',r=>r.fulfill({json:{version:1,can_configure:true,sec_configured:false,configuration_origin:'none',sources:[]}}));
 await page.route('**/api/research/financials/**',r=>{const u=new URL(r.request().url());const ticker=u.pathname.split('/').pop();const market=u.searchParams.get('market');return r.fulfill({json:snapshot(ticker,market,ticker==='FPT'?'70112825100710':ticker==='HPG'?'156116094618482':'123456789')});});
});

test('company selection automatically fills the actual table without a source picker',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/#investment-research');
 await expect(page.locator('.ir-financial-table').getByTitle('123,456,789 USD',{exact:true})).toBeVisible();
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).fill('FPT');
 await page.locator('.ir-search-results button').filter({hasText:'FPT'}).click();
 const table=page.locator('.ir-financial-table');
 await expect(table.getByTitle('70,112,825,100,710 VND',{exact:true})).toBeVisible();
 await expect(table).toContainText('FY 2025');
 await expect(table).toContainText('16.02 %');
 await expect(table.getByTitle('123,456,789 USD',{exact:true})).toHaveCount(0);
 await expect(page.locator('.financial-sources')).toContainText('CafeF');
 await expect(page.locator('.financial-sources select')).toHaveCount(0);
 await expect(page.locator('.financial-sources details')).not.toHaveAttribute('open','');
 await expect(table.getByTitle('The source does not provide reconciled EBITDA.')).toBeVisible();
 await expect(table.getByTitle('Capital expenditure does not reconcile with the cash-flow statement.')).toBeVisible();
 await page.locator('.ir-bottom-grid').screenshot({path:'artifacts/automatic-financials-desktop.png'});
 expect(errors).toEqual([]);
});

test('top search Enter also changes the company and loads new figures',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/#investment-research');
 const search=page.getByRole('textbox',{name:'Search companies',exact:true});
 await search.fill('HPG');await search.press('Enter');
 await expect(page.locator('.ir-company-tags')).toContainText('HPG');
 await expect(page.locator('.ir-financial-table').getByTitle('156,116,094,618,482 VND',{exact:true})).toBeVisible();
 await expect(page.getByRole('combobox',{name:'Company market',exact:true})).toHaveValue('VN');
 expect(errors).toEqual([]);
});

test('submitting a known Vietnamese ticker infers its market',async({page})=>{
 await page.goto('/#investment-research');
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).fill('FPT');
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).press('Enter');
 await expect(page.locator('.ir-company-tags')).toContainText('FPT');
 await expect(page.locator('.ir-financial-table').getByTitle('70,112,825,100,710 VND',{exact:true})).toBeVisible();
});

test('reviewed values take precedence per metric while missing values fill from provider',async({page})=>{
 await page.route('**/api/research/company/**',r=>r.fulfill({json:{...empty,status:'READY',metrics:{revenue:{...money('42','USD'),period_type:'TTM'}}}}));
 await page.goto('/#investment-research');
 const table=page.locator('.ir-financial-table');
 await expect(table).toContainText('42 USD');
 await expect(table).toContainText('TTM');
 await expect(table).toContainText('16.02 %');
 await expect(table.getByTitle('123,456,789 USD',{exact:true})).toHaveCount(0);
});

test('stale public data is excluded',async({page})=>{
 await page.route('**/api/research/financials/**',r=>r.fulfill({json:snapshot('AAPL','US','123456789',{cache_status:'STALE'})}));
 await page.goto('/#investment-research');
 await expect(page.locator('.financial-sources')).toContainText('saved copy is stale');
 await expect(page.locator('.ir-financial-table').getByTitle('123,456,789 USD',{exact:true})).toHaveCount(0);
});

test('failed new company request never leaves previous company figures',async({page})=>{
 await page.goto('/#investment-research');
 await expect(page.locator('.ir-financial-table').getByTitle('123,456,789 USD',{exact:true})).toBeVisible();
 await page.route('**/api/research/financials/FPT?*',r=>r.fulfill({status:422,json:{reason_code:'PROVIDER_UNAVAILABLE'}}));
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).fill('FPT');
 await page.locator('.ir-search-results button').filter({hasText:'FPT'}).click();
 await expect(page.locator('.financial-sources')).toContainText('temporarily unavailable');
 await expect(page.locator('.ir-financial-table').getByTitle('123,456,789 USD',{exact:true})).toHaveCount(0);
});

test('late response from old company cannot overwrite new selection',async({page})=>{
 let release,arrived;const pending=new Promise(resolve=>release=resolve);const requested=new Promise(resolve=>arrived=resolve);
 await page.route('**/api/research/financials/AAPL?*',async r=>{arrived();await pending;try{await r.fulfill({json:snapshot()});}catch{}});
 await page.goto('/#investment-research');await requested;
 await page.getByRole('textbox',{name:'Search companies',exact:true}).fill('FPT');
 await page.getByRole('textbox',{name:'Search companies',exact:true}).press('Enter');
 await expect(page.locator('.ir-financial-table').getByTitle('70,112,825,100,710 VND',{exact:true})).toBeVisible();
 release();
 await expect(page.locator('.ir-company-tags')).toContainText('FPT');
 await expect(page.locator('.ir-financial-table').getByTitle('123,456,789 USD',{exact:true})).toHaveCount(0);
});

test('missing SEC contact has no historical fallback and saving retries automatically',async({page})=>{
 let configured=false,posted;
 await page.route('**/api/research/financials/**',r=>configured?r.fulfill({json:snapshot()}):r.fulfill({status:422,json:{reason_code:'SEC_USER_AGENT_NOT_CONFIGURED'}}));
 await page.route('**/api/admin/financial-sources',r=>{posted=r.request().postDataJSON();configured=true;return r.fulfill({json:{version:1,can_configure:true,sec_configured:true,configuration_origin:'local'}});});
 await page.goto('/#investment-research');
 const panel=page.locator('.financial-sources');
 await expect(panel).toContainText('contact email once');
 await expect(page.locator('.ir-financial-table').getByTitle('123,456,789 USD',{exact:true})).toHaveCount(0);
 await panel.locator('summary').click();
 await panel.getByLabel('Contact email').fill('contact@example.com');
 await panel.getByRole('button',{name:'Save connection settings'}).click();
 await expect(page.locator('.ir-financial-table').getByTitle('123,456,789 USD',{exact:true})).toBeVisible();
 expect(posted).toEqual({email:'contact@example.com'});
});

test('Vietnamese company search and data status fit a phone',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.addInitScript(()=>localStorage.setItem('pasion-preferences',JSON.stringify({language:'vi',theme:'light'})));
 await page.goto('/#investment-research');
 await page.getByRole('textbox',{name:'Tìm công ty để phân tích',exact:true}).fill('FPT');
 await page.locator('.ir-search-results button').filter({hasText:'FPT'}).click();
 await expect(page.locator('.financial-sources')).toContainText('Đã tự động tải số liệu');
 await expect(page.locator('.ir-financial-table').getByTitle('70.112.825.100.710 VND',{exact:true})).toBeVisible();
 for(const selector of ['.ir-company-search','.financial-sources'])expect(await page.locator(selector).evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
 await page.locator('.ir-company-search').screenshot({path:'artifacts/automatic-financials-mobile.png'});
});

test('original valuation-first layout and every financial tool are available',async({page})=>{
 await page.goto('/#investment-research');
 await expect(page.locator('.ir-model-card')).toHaveCount(5);
 for(const model of ['DCF','P/E','DDM','Gordon','Asset-based'])await expect(page.getByRole('button',{name:'Calculate '+model+' →',exact:true})).toBeVisible();
 const order=await page.locator('.investment-research').evaluate(root=>[...root.children].map(e=>e.className));
 expect(order.indexOf('ir-top-grid')).toBeLessThan(order.indexOf('ir-model-section'));
 expect(order.indexOf('ir-model-section')).toBeLessThan(order.indexOf('ir-bottom-grid'));
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).fill('FPT');
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).press('Enter');
 await expect(page.locator('.ir-financial-table').getByTitle('70,112,825,100,710 VND',{exact:true})).toBeVisible();
 await page.locator('.investment-research').screenshot({path:'artifacts/automatic-financials-restored.png'});
});

test('all source lines are browsable and CSV downloads original units',async({page})=>{
 await page.goto('/#investment-research');
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).fill('FPT');
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).press('Enter');
 await page.getByRole('button',{name:'All indicators & statements →'}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog).toContainText('195 source statement lines');
 await expect(dialog.getByRole('rowheader',{name:'Gross margin',exact:true})).toBeVisible();
 await dialog.getByRole('button',{name:'Income statement',exact:true}).click();
 await dialog.getByLabel('Monetary scale').selectOption('1');
 await dialog.getByLabel('Find an indicator').fill('Doanh thu hoạt động tài chính');
 await expect(dialog).toContainText('2,977,156,356,773');
 const download=page.waitForEvent('download');await dialog.getByRole('button',{name:'Download CSV',exact:true}).click();
 expect((await download).suggestedFilename()).toBe('FPT-income.csv');
 await dialog.screenshot({path:'artifacts/automatic-financials-statements.png'});
});

test('P/E calculator prefills actual EPS, updates the chart and clears on issuer change',async({page})=>{
 await page.goto('/#investment-research');
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).fill('FPT');
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).press('Enter');
 await expect(page.locator('.ir-financial-table').getByTitle('70,112,825,100,710 VND',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Calculate P/E →',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByLabel('EPS (report period)',{exact:false})).toHaveValue('5216');
 await dialog.getByLabel('Target P/E multiple').fill('12');
 await dialog.getByRole('button',{name:'Calculate scenario',exact:true}).click();
 await expect(dialog.locator('.ir-calculator-result')).toContainText('62,592 VND/share');
 await dialog.getByRole('button',{name:'Close dialog',exact:true}).click();
 await expect(page.locator('.ir-model-card').filter({has:page.getByRole('heading',{name:'P/E',exact:true})})).toContainText('Your scenario');
 await page.getByRole('textbox',{name:'Search companies',exact:true}).fill('HPG');
 await page.getByRole('textbox',{name:'Search companies',exact:true}).press('Enter');
 await expect(page.locator('.ir-company-tags')).toContainText('HPG');
 await expect(page.locator('.ir-model-grid')).not.toContainText('62,592');
});

test('original PDF report downloads are scoped to the selected company',async({page})=>{
 const id='a'.repeat(24);
 await page.route('**/api/research/reports/FPT?*',r=>r.fulfill({json:{version:1,ticker:'FPT',market:'VN',reports:[{id,title:'FPT consolidated annual report 2025',period:'CN/2025',provider:'CafeF',format:'PDF',download_status:'SAVED',bytes:2048,url:'https://cafef.vn/du-lieu/'}]}}));
 await page.route('**/api/research/reports/FPT/'+id+'?*',r=>r.fulfill({body:'%PDF-1.7\nTest filing',headers:{'Content-Type':'application/pdf','Content-Disposition':'attachment; filename="FPT-2025.pdf"'}}));
 await page.goto('/#investment-research');
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).fill('FPT');
 await page.getByRole('textbox',{name:'Financial company search',exact:true}).press('Enter');
 await page.getByRole('button',{name:'Open / download reports →'}).click();
 const dialog=page.getByRole('dialog');await expect(dialog).toContainText('Saved on this server');
 const download=page.waitForEvent('download');await dialog.getByRole('link',{name:'Download PDF',exact:true}).click();
 expect((await download).suggestedFilename()).toBe('FPT-2025.pdf');
});
