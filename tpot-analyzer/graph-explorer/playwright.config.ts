import { defineConfig, devices } from '@playwright/test';
import fs from 'node:fs';

/**
 * IMPORTANT: The Python backend must be running before tests!
 * Start it with: cd tpot-analyzer && python -m src.server
 * 
 * NOTE: Cluster builds take ~57s on first load (71k nodes).
 * Tests use 180s timeout to accommodate this.
 */

function resolveChromiumExecutablePath(): string | undefined {
  const envPath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  const candidates = [
    envPath,
    // Prefer system browsers to avoid Playwright's downloaded browser cache.
    '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
  ].filter(Boolean) as string[];

  for (const candidate of candidates) {
    try {
      if (candidate && fs.existsSync(candidate)) return candidate;
    } catch {
      // ignore
    }
  }
  return undefined;
}

const chromiumExecutablePath = resolveChromiumExecutablePath();

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
    baseURL: 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        ...(chromiumExecutablePath
          ? {
              launchOptions: {
                executablePath: chromiumExecutablePath,
              },
            }
          : {}),
      },
    },
  ],
  webServer: process.env.PW_NO_SERVER
    ? undefined
    : {
        command: 'npm run dev -- --host 127.0.0.1 --port 5173 --strictPort',
        url: 'http://127.0.0.1:5173',
        reuseExistingServer: !process.env.CI,
        timeout: 120 * 1000,
      },
});
