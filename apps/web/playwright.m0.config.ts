import { defineConfig, devices } from "@playwright/test";

const fixtures = process.env.M0_FIXTURES === "true";
const port = fixtures ? 5188 : 5187;
export default defineConfig({
  testDir: "./src/app/__tests__",
  timeout: 30_000,
  workers: 1,
  reporter: "list",
  outputDir: fixtures ? "test-results/m0-fixtures" : "test-results/m0",
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: fixtures ? "m0-fixtures" : "m0-real-mode", use: { ...devices["Desktop Chrome"], channel: process.env.M0_BROWSER_CHANNEL || "chrome" } }],
  webServer: {
    command: `npm run dev -- --port ${port} --strictPort`, url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    env: { VITE_TC_FIXTURES: String(fixtures), VITE_TC_FIXTURE_SCENARIO: process.env.M0_SCENARIO || "success" },
  },
});
