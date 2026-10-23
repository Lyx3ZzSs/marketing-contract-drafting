import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:15173',
    channel: process.env.E2E_CHANNEL,
    trace: 'retain-on-failure',
  },
  reporter: 'list',
  workers: 1,
})
