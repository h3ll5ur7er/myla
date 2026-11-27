import { defineConfig, devices } from '@playwright/test';

// The built site (npm run build -- --base-href /myla/), served as GitHub
// Pages serves it, in Chromium (MYLA-635).
export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  fullyParallel: true,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:4310/myla/',
    trace: 'off',
    // a Chromium of another Playwright's (PW_CHROMIUM=/opt/pw-browsers/chromium)
    launchOptions: process.env['PW_CHROMIUM'] ? { executablePath: process.env['PW_CHROMIUM'] } : {},
  },
  webServer: {
    command: 'node scripts/serve.mjs --port 4310 --base /myla/',
    url: 'http://localhost:4310/myla/',
    reuseExistingServer: !process.env['CI'],
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
