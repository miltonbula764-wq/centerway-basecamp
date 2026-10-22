import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: ".",
  testMatch: "browser.spec.mjs",
  workers: 1,
  retries: 0,
  timeout: 60000,
  reporter: "list",
  outputDir: "../results-connected",
  use: {
    baseURL: "http://127.0.0.1:5173",
    browserName: "chromium",
    viewport: { width: 390, height: 844 },
    trace: "off",
    screenshot: "off",
    video: "off",
    ...(process.env.CW_BROWSER_BIN
      ? { launchOptions: { executablePath: process.env.CW_BROWSER_BIN } }
      : {}),
  },
  webServer: {
    command: "cd ../.. && node e2e/connected/vite.mjs",
    url: "http://127.0.0.1:5173",
    timeout: 120000,
    reuseExistingServer: false,
  },
});
