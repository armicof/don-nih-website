import { defineConfig } from '@playwright/test';

if (!process.env.E2E_BASE_URL || !process.env.E2E_ADMIN_EMAIL || !process.env.E2E_ADMIN_PASSWORD) {
  throw new Error('Run npm run test:e2e. The runner owns the temporary database, server, and generated accounts.');
}

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 120000,
  globalTimeout: 300000,
  expect: { timeout: 10000 },
  outputDir: './e2e/results',
  reporter: [['list'], ['html', { outputFolder: 'e2e/report', open: 'never' }]],
  use: {
    browserName: 'chromium',
    baseURL: process.env.E2E_BASE_URL,
    locale: 'id-ID',
    timezoneId: 'Asia/Jakarta',
    actionTimeout: 10000,
    navigationTimeout: 15000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : {},
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { viewport: { width: 360, height: 800 }, isMobile: true, hasTouch: true } },
  ],
});
