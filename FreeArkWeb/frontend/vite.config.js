import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { copyFileSync, existsSync, mkdirSync } from 'fs'
import { resolve, join, dirname } from 'path'

// 自定义插件：在构建完成后复制building_data.js
function copyBuildingDataPlugin() {
  return {
    name: 'copy-building-data',
    closeBundle() {
      // 方法1：从src/data复制
      const srcPath1 = join(__dirname, 'src', 'data', 'building_data.js')
      // 方法2：从根目录复制（备选方案）
      const srcPath2 = join(__dirname, 'building_data.js')
      const distPath = join(__dirname, 'dist', 'building_data.js')
      
      // 确保dist目录存在
      const distDir = dirname(distPath)
      if (!existsSync(distDir)) {
        try {
          mkdirSync(distDir, { recursive: true })
          console.log(`✅ 创建dist目录: ${distDir}`)
        } catch (error) {
          console.error(`❌ 创建dist目录失败: ${error.message}`)
        }
      }
      
      // 尝试使用第一个源文件路径
      if (existsSync(srcPath1)) {
        try {
          copyFileSync(srcPath1, distPath)
          console.log(`✅ 成功将building_data.js从${srcPath1}复制到${distPath}`)
          return // 成功后返回，不尝试备选路径
        } catch (error) {
          console.error(`❌ 从${srcPath1}复制building_data.js失败: ${error.message}`)
          console.log(`尝试使用备选路径...`)
        }
      } else {
        console.warn(`⚠️  源文件不存在: ${srcPath1}`)
      }
      
      // 如果第一个路径失败，尝试第二个源文件路径
      if (existsSync(srcPath2)) {
        try {
          copyFileSync(srcPath2, distPath)
          console.log(`✅ 成功将building_data.js从${srcPath2}复制到${distPath}`)
        } catch (error) {
          console.error(`❌ 从${srcPath2}复制building_data.js失败: ${error.message}`)
          console.warn(`⚠️  复制building_data.js失败，但构建过程将继续`)
        }
      } else {
        console.warn(`⚠️  源文件不存在: ${srcPath2}`)
        console.warn(`⚠️  无法复制building_data.js，但构建过程将继续`)
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