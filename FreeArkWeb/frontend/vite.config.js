import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { copyFileSync, existsSync } from 'fs'
import { resolve, join } from 'path'

// 自定义插件：在构建完成后复制building_data.js
function copyBuildingDataPlugin() {
  return {
    name: 'copy-building-data',
    closeBundle() {
      const srcPath = join(__dirname, 'src', 'data', 'building_data.js')
      const distPath = join(__dirname, 'dist', 'building_data.js')
      
      // 检查源文件是否存在
      if (existsSync(srcPath)) {
        try {
          // 复制文件
          copyFileSync(srcPath, distPath)
          console.log(`✅ 成功将building_data.js从${srcPath}复制到${distPath}`)
        } catch (error) {
          console.error(`❌ 复制building_data.js失败: ${error.message}`)
        }
      } else {
        console.warn(`⚠️  源文件不存在: ${srcPath}`)
      }
    }
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    copyBuildingDataPlugin() // 添加自定义复制插件
  ],
  server: {
    port: 8080,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        home: resolve(__dirname, 'home.html')
      }
    }
  }
})