import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

export default defineConfig({
  plugins: [uni()],
  // 统一输出到 dist/build/mp-weixin（dev 和 build 都用这个目录，
  // 微信开发者工具直接打开此目录即可）
  build: {
    outDir: 'dist/build/mp-weixin',
  },
})
