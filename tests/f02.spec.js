import {test, expect} from '@playwright/test';

test('F02 keeps samples distinct and suppresses unavailable provider values', async ({page}) => {
  await page.route('**/api/session', route => route.fulfill({json: {authenticated:true, isAdmin:false, user:{name:'F02',email:'f02@example.com'}}}));
  await page.route('**/api/market/summary?*', route => route.fulfill({json: {version:1,mode:'provider',status:'UNAVAILABLE',reason:'PROVIDER_NOT_READY',quotes:[]}}));
  await page.goto('/');
  const pulse = page.locator('.market-pulse-card');
  await expect(pulse.getByText('Sample data · no live feed')).toBeVisible();
  await expect(pulse.locator('.market-evidence').first()).toContainText('Sample');
  await pulse.getByLabel('Market data mode').selectOption('provider');
  await expect(pulse.locator('.market-pulse-value').first()).toHaveText('—');
  await expect(pulse.locator('.market-evidence').first()).toContainText('UNAVAILABLE');
  await expect(pulse.locator('.price-chart')).toHaveCount(0);
  await pulse.getByLabel('Market data mode').selectOption('demo');
  await expect(pulse.locator('.market-pulse-value').first()).not.toHaveText('—');
  await expect(pulse.locator('.market-evidence').first()).toContainText('Pasion demo fixture');
});

test('F02 provider quotes expire without showing an illustrative chart', async ({page}) => {
  await page.route('**/api/session', route => route.fulfill({json:{authenticated:true,isAdmin:false,user:{name:'F02',email:'f02@example.com'}}}));
  await page.route('**/api/market/summary?*', route => route.fulfill({json:{version:1,mode:'provider',status:'READY',quotes:[{
    ticker:'VNINDEX',origin:'ACTUAL',status:'READY',source:'Test provider',price:9999,change:0,
    as_of:new Date().toISOString(),expires_at:new Date(Date.now()+2500).toISOString()
  }]}}));
  await page.goto('/');
  const pulse = page.locator('.market-pulse-card');
  await pulse.getByLabel('Market data mode').selectOption('provider');
  await expect(pulse.locator('.market-pulse-value').first()).toHaveText('9,999.00');
  await expect(pulse.locator('.price-chart')).toHaveCount(0);
  await expect(pulse.locator('.market-evidence').first()).toContainText('STALE', {timeout:6000});
  await expect(pulse.locator('.market-pulse-value').first()).toHaveText('—');
});
