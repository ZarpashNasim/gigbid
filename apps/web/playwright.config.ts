import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:3100",
    launchOptions: { executablePath: process.env.CHROME_PATH || undefined },
    screenshot: "only-on-failure",
  },
  webServer: [
    { command: "cd ../.. && python -m uvicorn --factory apps.api.e2e_server:build --port 8100",
      url: "http://localhost:8100/health", reuseExistingServer: true, timeout: 60_000 },
    { command: "API_URL=http://localhost:8100 npx next dev -p 3100",
      url: "http://localhost:3100", reuseExistingServer: true, timeout: 120_000 },
  ],
});
