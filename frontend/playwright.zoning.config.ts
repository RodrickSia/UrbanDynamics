import { defineConfig } from '@playwright/test';

// Run a local API on 8087 with an isolated ZONING_DATA_DIR before this suite.
export default defineConfig({
  testDir: './tests/zoning', testMatch: 'zoning.spec.ts', timeout: 60000, workers: 1,
  use: { baseURL: 'http://127.0.0.1:5178', viewport: { width: 1440, height: 1000 },
    launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] }, screenshot: 'only-on-failure' },
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 5178', url: 'http://127.0.0.1:5178',
    reuseExistingServer: true, env: { ...process.env, VITE_GOONG_MAPTILES_KEY: 'playwright-test-key', API_PROXY_TARGET: 'http://127.0.0.1:8087' },
    stdout: 'ignore', stderr: 'ignore' },
});
