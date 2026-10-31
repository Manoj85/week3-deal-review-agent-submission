import { defineConfig } from "@playwright/test";
import { mkdirSync, mkdtempSync } from "node:fs";
import { resolve } from "node:path";
const work = resolve("../work");
mkdirSync(work, { recursive: true });
const data = mkdtempSync(resolve(work, "ui-e2e-"));
const python = resolve(
  process.platform === "win32"
    ? "../venv/Scripts/python.exe"
    : "../venv/bin/python",
);
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  fullyParallel: false,
  timeout: 45000,
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 1000 },
  },
  webServer: [
    {
      command: `"${python}" -m uvicorn backend.app.main:app --app-dir .. --host 127.0.0.1 --port 8014`,
      url: "http://127.0.0.1:8014/health",
      reuseExistingServer: false,
      env: { EXTRACTION_MODE: "offline_sample_parser", REVIEW_DATA_DIR: data },
    },
    {
      command: "npm run dev -- --port 5174",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      env: { LOAN_API_TARGET: "http://127.0.0.1:8014" },
    },
  ],
});
