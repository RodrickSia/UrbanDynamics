import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  testMatch: '**/backend-api.deploy.ts',
  timeout: 30000,
  workers: 1,
  use: {
    baseURL: process.env.BACKEND_E2E_BASE_URL ?? 'http://127.0.0.1:8080',
  },
});
