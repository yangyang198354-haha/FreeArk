import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('.', import.meta.url)).replace(/[\\/]$/, '')

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': root },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.js'],
    include: ['tests/chat-input-bar.spec.js', 'tests/chat-input-e2e.spec.js'],
  },
})
