// === TASK:WP-500:START ===
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { configDefaults } from 'vitest/config'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const envDir = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
  const env = loadEnv(mode, envDir, '')
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    envDir,
    plugins: [react()],
    server: {
      proxy: {
        '/v1': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      // === TASK:WP-602:START ===
      // Browser specs are executed only by the Playwright runner.
      exclude: [...configDefaults.exclude, 'src/e2e/**'],
      // === TASK:WP-602:END ===
    },
  }
})
// === TASK:WP-500:END ===
