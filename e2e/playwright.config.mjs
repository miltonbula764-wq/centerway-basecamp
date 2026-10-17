import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', fullyParallel: false, workers: 1, retries: 0,
  timeout: 45000, expect: { timeout: 10000 },
  reporter: [['list'], ['html', { outputFolder: 'report', open: 'never' }]],
  outputDir: 'results',
  use: { baseURL: 'http://127.0.0.1:5173', browserName: 'chromium',
    viewport: { width: 1280, height: 900 }, trace: 'off', screenshot: 'only-on-failure', video: 'off' },
  webServer: { command: 'cd .. && bun run dev --config e2e/vite.config.ts --host 127.0.0.1 --port 5173',
    url: 'http://127.0.0.1:5173', timeout: 120000, reuseExistingServer: false },
});
