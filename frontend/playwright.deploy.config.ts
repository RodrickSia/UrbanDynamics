import { defineConfig } from '@playwright/test';
import config from './playwright.config';

export default defineConfig({
  ...config,
  testMatch: '**/*.deploy.ts',
  timeout: 90000,
  use: { ...config.use, baseURL: process.env.DEPLOY_BASE_URL ?? 'http://127.0.0.1:51873' },
  webServer: undefined,
});
