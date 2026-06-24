import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'

// 工程根（miniprogram/），用于解析 `@/` 别名（与 uni-app 一致）
const root = fileURLToPath(new URL('.', import.meta.url)).replace(/[\\/]$/, '')

export default defineConfig({
  resolve: {
    alias: { '@': root },
  },
  test: {
    environment: 'node',
    globals: true,
    setupFiles: ['./tests/setup.js'],
    // 只跑纯逻辑单测（utils/store/api）；.vue 组件与 e2e 不在此层
    include: ['tests/**/*.spec.js'],
  },
})
