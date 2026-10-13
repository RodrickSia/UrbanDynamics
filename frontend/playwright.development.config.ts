import { defineConfig } from '@playwright/test';
import zoning from './playwright.zoning.config';

// Pair with backend/tests/development_testserver.py on 8087 and isolated SQLite storage.
export default defineConfig({ ...zoning, testMatch: 'development.spec.ts', timeout: 120000 });
