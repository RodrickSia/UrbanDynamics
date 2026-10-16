import { defineConfig } from '@playwright/test';
import development from './playwright.development.config';

// Isolated fixture API on 8037; do not reuse the team's local demo ports.
export default defineConfig({
  ...development,
  testMatch: 'simulation.spec.ts',
  use: {...development.use, baseURL:'http://127.0.0.1:5179', channel:'msedge'},
  webServer: {command:'npm run dev -- --host 127.0.0.1 --port 5179', url:'http://127.0.0.1:5179',
    reuseExistingServer:true, env:{...process.env,VITE_GOONG_MAPTILES_KEY:'playwright-test-key',API_PROXY_TARGET:'http://127.0.0.1:8037'},
    stdout:'ignore',stderr:'ignore'},
});
