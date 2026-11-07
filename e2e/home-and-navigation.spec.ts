import { test, expect } from '@playwright/test';

test.describe('ZENDOC 2.0 Landing Page & Global Navigation', () => {
  test('renders homepage with brand, emergency banner, and key capabilities', async ({ page }) => {
    await page.goto('/');

    // Check brand header
    await expect(page.locator('header')).toContainText('ZENDOC');
    await expect(page.locator('header')).toContainText('2.0');

    // Check emergency banner hotlines
    await expect(page.locator('body')).toContainText('102');
    await expect(page.locator('body')).toContainText('108');
    await expect(page.locator('body')).toContainText('112');

    // Check footer disclaimer
    await expect(page.locator('footer')).toContainText('ZENDOC is an educational and coordination tool');
  });

  test('navbar provides direct navigation to key portals', async ({ page }) => {
    await page.goto('/');

    // Desktop navbar navigation items
    const nav = page.locator('header nav');
    await expect(nav).toContainText('Dashboard');
    await expect(nav).toContainText('Find Care');
    await expect(nav).toContainText('Appointments');
    await expect(nav).toContainText('Health Memory');
    await expect(nav).toContainText('ZENDOC AI');
    await expect(nav).toContainText('Trust Center');
  });
});
