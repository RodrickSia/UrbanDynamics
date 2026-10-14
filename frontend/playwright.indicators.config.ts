import { defineConfig } from '@playwright/test';
import zoning from './playwright.zoning.config';

// Pair with backend/tests/indicators_testserver.py and isolated plan storage.
export default defineConfig({ ...zoning, testMatch: 'indicators.spec.ts' });
