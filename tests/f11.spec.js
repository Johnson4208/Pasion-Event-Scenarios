import {test,expect} from '@playwright/test';

test.beforeEach(async({page})=>{await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F11',email:'f11@example.com'}}}));});
test('F11 missing feeds remain visible and samples require explicit selection',async({page})=>{
 await page.route('**/api/research/news',r=>r.fulfill({json:{version:1,status:'UNAVAILABLE',origin:'2026-10-13T00:00:00Z',coverage:[],articles:[],bookmarks:[]}}));
 await page.route('**/api/research/news/proposals',r=>r.fulfill({json:{version:1,proposals:[]}}));
 await page.goto('/');await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Company News',exact:true}).click();
 await expect(page.locator('.news-evidence')).toContainText('No permitted feeds registered');
 await expect(page.locator('.news-evidence')).toContainText('Headlines never change EPS');
 await page.getByLabel('News data mode').selectOption('sample');await expect(page.locator('.company-news-story-meta').first()).toContainText('Sample story');
});

test('F11 claim drawer preserves counterevidence and submits a proposed driver review',async({page})=>{
 const a={id:'story',cluster_id:'cluster',category:'Earnings',provider:'Reviewed fixture',title:'Issuer revenue announcement',summary:'Reported revenue context',url:'https://example.com/story',published_at:'2026-10-12T00:00:00Z',ingested_at:'2026-10-12T01:00:00Z',known_at:'2026-10-13T00:00:00Z',revision:'original',tickers:['AAPL'],claims:[{id:'claim',text:'Revenue increased',excerpt:'Reported revenue increased',locator:'Paragraph 2',review:{status:'SUPPORTED',review_note:'Compared issuer filing',relations:[{stance:'SUPPORTING',excerpt:'Issuer reported higher revenue',url:'https://example.com/filing',provider:'Issuer filing',explanation:'Same fiscal period'}]}}]};
 let bookmark=null,proposal=null;
 await page.route('**/api/research/news',r=>r.fulfill({json:{version:1,status:'PARTIAL',origin:a.known_at,coverage:[{id:'provider',name:'Reviewed fixture',status:'GAP',coverage:'Issuer coverage',last_known_at:a.known_at}],articles:[a,{...a,id:'syndicated'}],bookmarks:[]}}));
 await page.route('**/api/research/news/proposals',r=>{if(r.request().method()==='POST'){proposal=r.request().postDataJSON();return r.fulfill({json:{version:1,proposal:{id:'proposed'}}});}return r.fulfill({json:{version:1,proposals:[]}});});
 await page.route('**/api/research/news/bookmarks',r=>{bookmark=r.request().postDataJSON();return r.fulfill({json:{version:1,saved:true}});});
 await page.goto('/');await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:'Company News',exact:true}).click();
 await expect(page.locator('.news-evidence-stories .company-news-card')).toHaveCount(1);
 await page.getByRole('button',{name:'Save Issuer revenue announcement'}).click();expect(bookmark.article_id).toBe('story');
 await page.getByRole('button',{name:'Inspect article claims'}).click();const drawer=page.getByRole('region',{name:'Article claim evidence'});
 await expect(drawer).toContainText('SUPPORTED');await expect(drawer).toContainText('Same fiscal period');await expect(drawer).toContainText(a.known_at);
 await drawer.getByLabel('driver',{exact:true}).fill('Revenue growth');await drawer.getByLabel('proposed change',{exact:true}).fill('Review operating outlook');await drawer.getByLabel('rationale',{exact:true}).fill('New filing context');
 await drawer.getByRole('button',{name:'Submit research review proposal'}).click();await expect(page.locator('.news-evidence')).toContainText('Driver proposal saved');
 expect(proposal.claim_id).toBe('claim');expect(proposal.ticker).toBe('AAPL');expect(proposal.proposed_change).toBe('Review operating outlook');
});

test('F11 admin records a separate driver-review decision',async({page})=>{
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:true,user:{name:'Admin',email:'admin@example.com'}}}));
 await page.route('**/api/admin/accounts',r=>r.fulfill({json:{accounts:[]}}));
 await page.route('**/api/admin/news/proposals',r=>r.fulfill({json:{version:1,proposals:[{id:'proposal',ticker:'AAPL',driver:'Revenue growth',proposed_change:'Review growth driver',rationale:'Filing context',source_url:'https://example.com/story',claim:{text:'Reported growth',review:{status:'SUPPORTED',relations:[]}}}]}}));
 let submitted;
 await page.route('**/api/admin/news/decide',r=>{submitted=r.request().postDataJSON();return r.fulfill({json:{version:1,decision:{decision:submitted.decision,note:submitted.note}}});});
 await page.goto('/#admin');await page.getByRole('navigation',{name:'Administration sections'}).getByRole('button',{name:'News research review'}).click();
 await expect(page.locator('.admin-page')).toContainText('does not change valuation');
 await page.getByLabel('Review decision').selectOption('APPROVED_FOR_DRIVER_REVIEW');await page.getByLabel('Review rationale').fill('Review operating driver with accepted finance facts');
 await page.getByRole('button',{name:'Record review decision'}).click();await expect(page.getByRole('status')).toContainText('APPROVED_FOR_DRIVER_REVIEW');
 expect(submitted.proposal_id).toBe('proposal');
});
