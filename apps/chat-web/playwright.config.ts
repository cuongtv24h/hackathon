// === TASK:WP-602:START ===
import { defineConfig } from '@playwright/test'

const runLive = process.env.E2E_LIVE === '1'

export default defineConfig({
  testDir: './src/e2e',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    browserName: 'chromium',
  },
  webServer: runLive ? [
    { command: 'py -m uvicorn apps.mock_his.main:app --host 127.0.0.1 --port 8001', cwd: '../..', url: 'http://127.0.0.1:8001/health', reuseExistingServer: true },
    { command: 'py -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000', cwd: '../..', url: 'http://127.0.0.1:8000/api/v1/docs', reuseExistingServer: true },
    { command: 'npm.cmd run dev -- --host 127.0.0.1', url: 'http://127.0.0.1:5173', reuseExistingServer: true },
    { command: 'npm.cmd run dev -- --host 127.0.0.1 --port 5174', cwd: '../admin-web', url: 'http://127.0.0.1:5174', reuseExistingServer: true },
  ] : {
    command: 'npm.cmd run dev -- --host 127.0.0.1',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,
  },
})
// === TASK:WP-602:END ===
