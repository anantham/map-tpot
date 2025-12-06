import { defineConfig, devices } from '@playwright/test';

/**
 * IMPORTANT: The Python backend must be running before tests!
 * Start it with: cd tpot-analyzer && python -m src.server
 * 
 * NOTE: Cluster builds take ~57s on first load (71k nodes).
 * Tests use 180s timeout to accommodate this.
 */

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  // 180s timeout for slow cluster builds (~57s + overhead)
  timeout: 180000,
  reporter: [
    ['html'],
    ['json', { outputFile: 'e2e/results/test-results.json' }]
  ],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev -- --port 5173 --strictPort',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
});
