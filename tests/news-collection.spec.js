import {test,expect} from '@playwright/test';

const article=(overrides={})=>({id:'saved-story',title:'Stored issuer revenue announcement',summary:'A stored source excerpt with its original publication date.',
 url:'https://example.org/issuer',published_at:'2026-10-20T08:00:00Z',known_at:'2026-10-21T08:00:00Z',provider:'Synthetic permitted source',category:'Earnings',tickers:['AAPL'],claims:[],...overrides});
const feed=(articles=[],coverage=[])=>({version:1,status:articles.length?'PARTIAL':'UNAVAILABLE',articles,coverage,bookmarks:[],origin:'2026-10-23T08:00:00Z'});
const newsroom=page=>page.locator('.company-news');
const collection=page=>page.getByRole('region',{name:'News collection status'});
async function open(page){await page.goto('/#company-news');await expect(newsroom(page)).toBeVisible();}

test.beforeEach(async({page})=>{
 await page.route('**/api/session',route=>route.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'News collection reviewer',email:'news-collection@example.invalid'}}}));
 await page.route('**/api/research/company/**',route=>route.fulfill({json:{status:'UNAVAILABLE'}}));
});

test('loading and storage failure do not masquerade as an empty library; retry loads stored records',async({page})=>{
 let calls=0,release;
 const pending=new Promise(resolve=>{release=resolve;});
 await page.route('**/api/research/news',async route=>{
  calls++;
  if(calls===1){await pending;await route.fulfill({status:503,json:{message:'Unavailable'}});}
  else await route.fulfill({json:feed([article()])});
 });
 await open(page);
 await expect(collection(page).getByRole('status')).toHaveText('Loading stored news…');
 await expect(newsroom(page).locator('.company-news-context>div').first().locator('strong')).toHaveText('—');
 await expect(newsroom(page)).not.toContainText('No stored articles in this news library.');
 release();
 await expect(collection(page).getByRole('alert')).toHaveText('Stored news is temporarily unavailable. Try again.');
 await expect(collection(page)).toContainText('The article count is unknown');
 await expect(newsroom(page)).not.toContainText('No stored articles in this news library.');
 await collection(page).getByRole('button',{name:'Retry loading news'}).click();
 await expect(collection(page)).toContainText('1 stored articles loaded');
 await expect(newsroom(page).getByRole('heading',{name:'Stored issuer revenue announcement'})).toBeVisible();
 await expect(newsroom(page).locator('.company-news-context>div').first().locator('strong')).toHaveText('1');
 await expect(newsroom(page)).not.toContainText('Illustrative feed');
 await expect(newsroom(page)).not.toContainText('Reviewed evidence');
});

test('expired authentication is shown separately from missing articles',async({page})=>{
 await page.route('**/api/research/news',route=>route.fulfill({status:401,json:{message:'Sign in'}}));
 await open(page);
 await expect(collection(page).getByRole('alert')).toHaveText('Sign in again to load your stored news.');
 await expect(newsroom(page).locator('.company-news-context>div').first().locator('strong')).toHaveText('—');
 await expect(newsroom(page)).not.toContainText('No stored articles in this news library.');
});

test('an empty stored library explains recovery and ingestion instead of suggesting filters',async({page})=>{
 await page.route('**/api/research/news',route=>route.fulfill({json:feed()}));
 await open(page);
 await expect(newsroom(page).getByRole('heading',{name:'No stored articles in this news library.'})).toBeVisible();
 await expect(collection(page)).toContainText('No permitted feeds registered in this news library.');
 await expect(collection(page)).toContainText('recover the data from the older project');
 await expect(collection(page)).toContainText('opening this page does not start an automatic collector');
 await expect(newsroom(page)).not.toContainText('No articles match these filters.');
});

test('registered-source gaps and restrictive filters preserve the true stored article count',async({page})=>{
 await page.route('**/api/research/news',route=>route.fulfill({json:feed([article()],
  [{id:'permitted',name:'Synthetic source archive',status:'GAP',last_known_at:'2026-10-21T08:00:00Z'}])}));
 await open(page);
 await expect(collection(page)).toContainText('1 stored articles loaded');
 await collection(page).getByText('1 registered news sources',{exact:true}).click();
 await expect(collection(page)).toContainText('Synthetic source archive');
 await expect(collection(page)).toContainText('No recent accepted arrival');
 await page.getByRole('textbox',{name:'Search companies',exact:true}).fill('no-matching-stored-story');
 await expect(newsroom(page).getByRole('heading',{name:'No articles match these filters.'})).toBeVisible();
 await expect(collection(page)).toContainText('1 stored articles loaded');
 await newsroom(page).getByRole('button',{name:'Clear filters',exact:true}).last().click();
 await expect(newsroom(page).getByRole('heading',{name:'Stored issuer revenue announcement'})).toBeVisible();
});

test('malformed responses fail visibly rather than silently presenting zero records',async({page})=>{
 await page.route('**/api/research/news',route=>route.fulfill({json:{version:1,articles:[{title:'Malformed secretless fixture'}]}}));
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await open(page);
 await expect(collection(page).getByRole('alert')).toHaveText('The news library returned an invalid response. Try again.');
 await expect(newsroom(page).locator('.company-news-context>div').first().locator('strong')).toHaveText('—');
 expect(errors).toEqual([]);
});

test('all five layouts retain the same stored articles and server bookmarks',async({page})=>{
 let bookmarked;
 await page.route('**/api/research/news',route=>route.fulfill({json:feed([article()])}));
 await page.route('**/api/research/news/bookmarks',route=>{
  bookmarked=route.request().postDataJSON();return route.fulfill({json:{version:1,saved:true}});
 });
 await open(page);
 await expect(newsroom(page).getByRole('heading',{name:'Stored issuer revenue announcement'})).toBeVisible();
 for(const index of [0,1,2,3,4]){
  const picker=page.locator('.layout-picker');
  const buttons=picker.getByRole('button');
  await expect(buttons).toHaveCount(5);
  await buttons.nth(index).click();
  await expect(newsroom(page).getByRole('heading',{name:'Stored issuer revenue announcement'})).toBeVisible();
 }
 await newsroom(page).getByRole('button',{name:'Save Stored issuer revenue announcement',exact:true}).click();
 expect(bookmarked).toEqual({article_id:'saved-story',saved:true});
 await expect(newsroom(page).getByRole('button',{name:'Unsave Stored issuer revenue announcement',exact:true})).toHaveAttribute('aria-pressed','true');
});
