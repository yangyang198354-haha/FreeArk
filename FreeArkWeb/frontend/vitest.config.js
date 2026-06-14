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
    // jsdom（非 happy-dom）：DOMPurify 官方按 jsdom 验证；happy-dom 下其 <table> 解析
    // 与 javascript: URI 消毒行为不符（实测 3 个用例假失败），jsdom 与真浏览器一致。
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.js', 'src/**/*.spec.js'],
  },
})
