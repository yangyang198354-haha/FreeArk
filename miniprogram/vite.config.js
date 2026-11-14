import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'
import fs from 'node:fs'
import path from 'node:path'

// uni's mp-weixin compiler does not copy root-level static files when the
// output directory is customized. Keep these files available to DevTools.
function copyStaticFilesPlugin() {
  let outputDir
  let projectRoot

  const copyStaticFiles = () => {
    const sourceDir = path.join(projectRoot, 'static')
    if (!outputDir || !fs.existsSync(sourceDir)) return

    fs.cpSync(sourceDir, path.join(outputDir, 'static'), { recursive: true })
  }

  return {
    name: 'copy-mp-weixin-static-files',
    configResolved(config) {
      projectRoot = config.root
      outputDir = path.resolve(config.root, config.build.outDir)
    },
    configureServer() {
      copyStaticFiles()
    },
    writeBundle() {
      copyStaticFiles()
    },
  }
}

export default defineConfig({
  plugins: [uni(), copyStaticFilesPlugin()],
  // 统一输出到 dist/build/mp-weixin（dev 和 build 都用这个目录，
  // 微信开发者工具直接打开此目录即可）
  build: {
    outDir: 'dist/build/mp-weixin',
    emptyOutDir: true,
  },
})
