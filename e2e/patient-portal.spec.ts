import { test, expect } from '@playwright/test';

test.describe('Patient Clinical Modules & Health Records', () => {
  test('patient dashboard loads clinical overview modules', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.locator('h1')).toContainText('Welcome back, Rahul Sharma');
  });

  test('health vitals page renders biomarkers tracker', async ({ page }) => {
    await page.goto('/vitals');
    await expect(page.locator('h1')).toContainText('Vitals & Health Biomarkers');
  });

  test('longitudinal health memory page loads timeline view', async ({ page }) => {
    await page.goto('/memory');
    await expect(page.locator('h1')).toContainText('Health Memory & Longitudinal Timeline');
  });

  test('medical records vault renders document list and upload link', async ({ page }) => {
    await page.goto('/records');
    await expect(page.locator('h1')).toContainText('Medical Records & Clinical Documents');
    await expect(page.locator('a[href="/records/upload"]')).toBeVisible();
  });

  test('trust center renders privacy and consent controls', async ({ page }) => {
    await page.goto('/trust-center');
    await expect(page.locator('h1')).toContainText('Consent & Trust Center');
  });
});
