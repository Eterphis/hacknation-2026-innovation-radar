import { defineConfig, devices } from "@playwright/test";
import type { ThemeOptions } from "./fixtures";

// Serwer pod testy:
//  - CI: compose w trybie demo, E2E_BASE_URL=http://localhost:8000 (job `e2e` w .github/workflows/ci.yml);
//  - lokalnie bez Dockera: webServer niżej (SQLite + `radar demo` + uvicorn na :8010).
const external = process.env.E2E_BASE_URL;
const port = process.env.E2E_PORT || "8010";
const baseURL = external || `http://127.0.0.1:${port}`;
const CI = !!process.env.CI;

const desktop = { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } };
const mobile = { ...devices["Pixel 5"], viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true };
// Funkcjonalne testy: tylko jasne projekty. Zrzuty i axe (routes, a11y): wszystkie cztery. layout: tylko 375 px.
const FUNCTIONAL = /(wizard|save-like|keyboard|demo)\.spec\.ts/;

export default defineConfig<ThemeOptions>({
  testDir: "./tests",
  outputDir: "./test-results/artifacts",
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  fullyParallel: true,
  workers: CI ? 2 : undefined,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report" }],
    ["json", { outputFile: "test-results/results.json" }],
    ["./reporters/flaky-warning.ts"],
  ],
  use: {
    baseURL,
    reducedMotion: "reduce",  // ruch wyłączony w testach (a test reduced-motion sprawdza, że CSS to respektuje)
    locale: "pl-PL",
    timezoneId: "Europe/Warsaw",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop-light", use: { ...desktop, colorScheme: "light", theme: "light" }, testIgnore: /layout\.spec\.ts/ },
    { name: "desktop-dark", use: { ...desktop, colorScheme: "dark", theme: "dark" }, testIgnore: [FUNCTIONAL, /layout\.spec\.ts/] },
    { name: "mobile-light", use: { ...mobile, colorScheme: "light", theme: "light" } },
    { name: "mobile-dark", use: { ...mobile, colorScheme: "dark", theme: "dark" }, testIgnore: FUNCTIONAL },
  ],
  webServer: external ? undefined : {
    command: "node scripts/serve.mjs",
    url: `${baseURL}/readyz`,
    reuseExistingServer: !CI,
    timeout: 180_000,
    env: { E2E_PORT: port },
  },
});
