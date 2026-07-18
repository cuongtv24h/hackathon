// === TASK:WP-500:START ===
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const envDir = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
  const env = loadEnv(mode, envDir, '')
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    envDir,
    // The Admin build is served by FastAPI below /admin/ in the VPS setup.
    base: '/admin/',
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
    },
  }
})
// === TASK:WP-500:END ===
