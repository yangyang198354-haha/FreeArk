import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'
import fs from 'node:fs'
import path from 'node:path'

const copyAdjutantAwayImage = {
  name: 'copy-adjutant-away-image',
  writeBundle() {
    const outputDir = path.resolve(__dirname, 'dist/build/mp-weixin/assets')
    fs.mkdirSync(outputDir, { recursive: true })
    fs.copyFileSync(
      path.resolve(__dirname, 'public/adjutant-away.png'),
      path.join(outputDir, 'adjutant-away.png'),
    )
  },
}

export default defineConfig({
  plugins: [uni(), copyAdjutantAwayImage],
  // 统一输出到 dist/build/mp-weixin（dev 和 build 都用这个目录，
  // 微信开发者工具直接打开此目录即可）
  build: {
    outDir: 'dist/build/mp-weixin',
  },
})
