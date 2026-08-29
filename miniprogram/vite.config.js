import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'
import fs from 'node:fs'
import path from 'node:path'

/**
 * uni-app 构建微信小程序时，项目根 static/ 目录下的新增文件不会被自动复制到
 * dist/build/mp-weixin/static/，导致模板里写 src="/static/xxx" 时渲染层报
 * "渲染层网络层错误 Failed to load image"。此插件在每次 closeBundle 时
 * 用 Windows 原生命令同步整个 static/ 目录，保证 100% 覆盖。
 * H5/其他平台无副作用。
 */
function copyStaticPlugin() {
  return {
    name: 'copy-static-for-mp-weixin',
    apply: 'build',
    closeBundle() {
      const root = process.cwd()
      const src = path.resolve(root, 'static')
      const outDir = 'dist/build/mp-weixin'
      const dest = path.resolve(root, outDir, 'static')
      if (!fs.existsSync(src)) return
      fs.mkdirSync(dest, { recursive: true })
      // 命令在 Windows PowerShell/CMD 均可运行：/E 复制所有子目录含空，
      // /H 含隐藏/系统，/Y 覆盖不提示，/I 目标不存在时当目录处理。
      try {
        const { execSync } = require('child_process')
        execSync(`xcopy "${src}" "${dest}" /E /H /Y /I`, { stdio: 'inherit' })
      } catch (e) {
        // 非 Windows 环境（Linux/macOS）fallback 到 cp -r
        if (process.platform !== 'win32') {
          const { execSync } = require('child_process')
          execSync(`cp -r "${src}/"* "${dest}/"`, { stdio: 'inherit' })
        } else {
          throw e
        }
      }
    },
  }
}

export default defineConfig({
  plugins: [uni(), copyStaticPlugin()],
  // 统一输出到 dist/build/mp-weixin（dev 和 build 都用这个目录，
  // 微信开发者工具直接打开此目录即可）
  build: {
    outDir: 'dist/build/mp-weixin',
  },
})
