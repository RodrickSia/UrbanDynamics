import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // Development only. Compose production already has the same-origin nginx proxy.
  server: {
    proxy: {
      '/api': {
        target:
          process.env.API_PROXY_TARGET ??
          loadEnv(mode, process.cwd(), 'API_PROXY_TARGET').API_PROXY_TARGET ??
          'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    },
  },
  build: {
    // MapLibre is isolated in an async WebGL chunk (~1.03 MB minified / 277 KB gzip).
    chunkSizeWarningLimit: 1100,
  },
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
  },
}));
