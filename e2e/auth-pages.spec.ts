import { test, expect } from '@playwright/test';

test.describe('Authentication & Registration UI Flows', () => {
  test('login page displays secure credentials form', async ({ page }) => {
    await page.goto('/login');

    await expect(page.locator('h1')).toContainText('Sign in to ZENDOC 2.0');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toContainText('Sign In');

    // Link to registration
    await expect(page.locator('a[href="/register"]')).toBeVisible();
  });

  test('registration page validates input constraints', async ({ page }) => {
    await page.goto('/register');

    await expect(page.locator('h1')).toContainText('Create Patient Account');

    const fullNameInput = page.locator('input[name="fullName"]');
    const emailInput = page.locator('input[name="email"]');
    const phoneInput = page.locator('input[name="phone"]');
    const passwordInput = page.locator('input[name="password"]');

    await expect(fullNameInput).toBeVisible();
    await expect(emailInput).toBeVisible();
    await expect(phoneInput).toBeVisible();
    await expect(passwordInput).toBeVisible();

    // Verify minimum password length constraint in DOM
    const minLength = await passwordInput.getAttribute('minlength');
    expect(minLength).toBe('10');
  });
});
