import { test, expect } from '@playwright/test';

test.describe('Healthcare Discovery & Find Care Directory', () => {
  test('renders verified healthcare provider and facility search filters', async ({ page }) => {
    await page.goto('/find-care');

    await expect(page.locator('h1')).toContainText('Healthcare Discovery & Finder');
    await expect(page.locator('body')).toContainText('Verified Clinicians');
    await expect(page.locator('body')).toContainText('Accredited Healthcare Facilities');

    // Search bar presence
    const searchBar = page.locator('input[placeholder*="Search by doctor"]');
    await expect(searchBar).toBeVisible();
  });
});
