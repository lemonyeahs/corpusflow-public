/// <reference types="node" />
import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

export default defineConfig({
  testDir: "./__tests__", workers: 1, timeout: 30_000, reporter: "list",
  outputDir: "../../../../../.local/training-center/browser-results",
  use: { baseURL: "http://127.0.0.1:5192", screenshot: "only-on-failure", trace: "retain-on-failure" },
  projects: [{ name: "datasets-chrome", use: { ...devices["Desktop Chrome"], channel: "chrome" } }],
  webServer: { command: "npm run dev -- --port 5192 --strictPort", cwd: fileURLToPath(new URL("../../../", import.meta.url)),
    url: "http://127.0.0.1:5192", reuseExistingServer: false, env: { VITE_TC_FIXTURES: "false" } },
});
