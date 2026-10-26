import {test,expect} from '@playwright/test';
test.setTimeout(60000);
test.beforeEach(async({page})=>{
 await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
});
async function member(page){
 await page.route('**/api/session',r=>r.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'Design Review',email:'design@example.test'}}}));
 await page.goto('/',{waitUntil:'domcontentloaded'});
 await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeVisible();
}
test('workspace retains keyboard search and theme switching with readable sidebar',async({page})=>{
 await member(page);
 await expect(page.locator('.home-sidebar')).toHaveCSS('background-color','rgb(255, 255, 255)');
 await page.keyboard.press('Control+k');await expect(page.getByRole('textbox',{name:'Search companies'})).toBeFocused();
 await page.getByRole('button',{name:'Switch to dark mode'}).click();await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
 await expect(page.getByRole('button',{name:'Dashboard',exact:true})).toHaveAttribute('aria-current','page');
 await page.getByRole('button',{name:'Switch to light mode'}).click();await expect(page.locator('html')).toHaveAttribute('data-theme','light');
});
test('mobile research routes retain navigation without page overflow',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.setViewportSize({width:390,height:844});await member(page);
 for(const name of ['Compare Companies','Stock Analytics','Indicators & VSA','Investment Research','Trade Planner','Portfolio Monitor','Company News','Event Scenarios','Macro Regime Monitor']){
  await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  const destination=page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name,exact:true});await destination.click();
  await expect(destination).toHaveAttribute('aria-current','page');
  await expect(page.locator('.workspace-page-content')).toHaveAttribute('aria-busy','false');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth),name).toBeLessThanOrEqual(390);
 }
 expect(errors).toEqual([]);
});
test('mobile sign-in preserves password visibility and registration controls',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.route('**/api/session',r=>r.fulfill({json:{authenticated:false}}));
 await page.goto('/#login',{waitUntil:'domcontentloaded'});
 const password=page.getByLabel('Password',{exact:true});await expect(password).toHaveAttribute('type','password');
 await page.getByRole('button',{name:'Show',exact:true}).click();await expect(password).toHaveAttribute('type','text');
 await page.getByRole('button',{name:'Register',exact:true}).click();await expect(page.getByLabel('Full name')).toBeVisible();
 await expect(page.getByLabel('Confirm password',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
