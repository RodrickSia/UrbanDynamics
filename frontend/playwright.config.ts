import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  timeout: 45000,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    viewport: { width: 1000, height: 700 },
    launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] },
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5173',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,
    env: { ...process.env, VITE_GOONG_MAPTILES_KEY: 'playwright-test-key' },
    // Vite may forward vendor console messages containing a public tile key.
    stdout: 'ignore',
    stderr: 'ignore',
  },
});
