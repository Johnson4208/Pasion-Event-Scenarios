import {test, expect} from '@playwright/test';

test('F01 preserves language and theme across reload and account navigation', async ({page}) => {
  await page.route('**/api/session', route => route.fulfill({json: {
    authenticated: true, isAdmin: false, user: {name: 'F01 Member', email: 'f01@example.com'}
  }}));
  await page.goto('/');
  await page.getByRole('button', {name: 'Switch to dark mode'}).click();
  await page.locator('.home-topbar .preference-language select').selectOption('es');
  await expect(page.locator('html')).toHaveAttribute('lang', 'es');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', 'es');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.goto('/#admin');
  await expect(page.locator('.admin-documents')).toHaveCount(0);
  await expect(page.locator('.admin-page')).toHaveCount(0);
  await expect(page.locator('html')).toHaveAttribute('lang', 'es');
});
