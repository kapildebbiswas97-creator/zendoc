import { test, expect } from '@playwright/test';

test.describe('ZENDOC AI Advisory & Emergency Triage Interception', () => {
  test('renders AI advisor interface with educational disclaimer', async ({ page }) => {
    await page.goto('/ai');

    await expect(page.locator('h1')).toContainText('ZENDOC AI Advisory Assistant');
    await expect(page.locator('body')).toContainText('AI is educational only');
    await expect(page.locator('input[placeholder*="Describe your health question"]')).toBeVisible();
  });

  test('intercepts acute life-threatening emergency and triggers instant hotline escalation', async ({ page }) => {
    await page.goto('/ai');

    const input = page.locator('input[placeholder*="Describe your health question"]');
    const sendButton = page.locator('button[type="submit"]');

    // Type acute red-flag emergency symptoms
    await input.fill('I have crushing chest pain radiating to my arm and difficulty breathing');
    await sendButton.click();

    // Verify emergency diversion banner appears
    await expect(page.locator('body')).toContainText('CRITICAL MEDICAL EMERGENCY DETECTED');
    await expect(page.locator('body')).toContainText('Call 102');
    await expect(page.locator('body')).toContainText('Call 108');
  });

  test('processes benign dietary inquiry with clinical advisory guidance', async ({ page }) => {
    await page.goto('/ai');

    const input = page.locator('input[placeholder*="Describe your health question"]');
    const sendButton = page.locator('button[type="submit"]');

    await input.fill('What is a healthy diet for general wellness?');
    await sendButton.click();

    // Verify response arrives with advisory
    await expect(page.locator('body')).toContainText('Nutritional Guidance');
  });
});
