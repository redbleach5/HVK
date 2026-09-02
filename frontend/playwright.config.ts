import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:8501'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ['list'],
    ['json', { outputFile: 'playwright-report/results.json' }],
  ],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    locale: 'ru-RU',
    ...devices['Desktop Chrome'],
  },
  projects: [
    { name: 'smoke', testMatch: /smoke\.spec\.ts/, timeout: 30_000 },
    { name: 'model', testMatch: /model\.spec\.ts/, timeout: 1_260_000 },
  ],
  expect: { timeout: 15_000 },
})
