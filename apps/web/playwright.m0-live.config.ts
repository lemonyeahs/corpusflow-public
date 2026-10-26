import { defineConfig, devices } from "@playwright/test";

const target = process.env.M0_LIVE_API;
if (!target || !/^http:\/\/127\.0\.0\.1:\d+$/.test(target)) throw new Error("Use scripts/verify_training_center_m0.py with its isolated API");
export default defineConfig({
  testDir: "./tests/m0-live", timeout: 30_000, workers: 1, reporter: "list",
  outputDir: "test-results/m0-live",
  use: { baseURL: "http://127.0.0.1:5191", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "m0-live", use: { ...devices["Desktop Chrome"], channel: process.env.M0_BROWSER_CHANNEL || "chrome" } }],
  webServer: {
    command: "npm run dev -- --port 5191 --strictPort", url: "http://127.0.0.1:5191", reuseExistingServer: false,
    env: { API_PROXY_TARGET: target, VITE_TC_FIXTURES: "false", VITE_API_BASE_URL: "/api/v1" },
  },
});
