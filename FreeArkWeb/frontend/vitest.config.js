/**
 * Vitest 配置 — FreeArk_ChatFormat 测试
 * @phase PHASE_07-09 (GROUP_D)
 * @author sub_agent_test_engineer
 */
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    include: ['src/**/*.test.js', 'src/**/*.spec.js'],
  },
})
