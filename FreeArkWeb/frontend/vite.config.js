import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { copyFileSync, existsSync, mkdirSync } from 'fs'
import { resolve, join, dirname } from 'path'

// 自定义插件：在构建完成后复制building_data.js
function copyBuildingDataPlugin() {
  return {
    name: 'copy-building-data',
    closeBundle() {
      // 总是从src/data复制
      const srcPath = join(__dirname, 'src', 'data', 'building_data.js')
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
      
      // 尝试使用源文件路径
      if (existsSync(srcPath)) {
        try {
          copyFileSync(srcPath, distPath)
          console.log(`✅ 成功将building_data.js从${srcPath}复制到${distPath}`)
        } catch (error) {
          console.error(`❌ 从${srcPath}复制building_data.js失败: ${error.message}`)
          console.warn(`⚠️  复制building_data.js失败，但构建过程将继续`)
        }
      } else {
        console.warn(`⚠️  源文件不存在: ${srcPath}`)
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
  // 配置服务器
  server: {
    port: 8080,
    // 添加中间件处理building_data.js请求
    configureServer(server) {
      server.middlewares.use('/building_data.js', (req, res, next) => {
        try {
          const fs = require('fs');
          const path = require('path');
          
          // 首先尝试直接从src/data目录读取文件
          const srcDataPath = path.join(__dirname, 'src', 'data', 'building_data.js');
          
          if (fs.existsSync(srcDataPath)) {
            // 确保返回正确的Content-Type
            res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
            // 直接读取并发送文件内容
            const fileContent = fs.readFileSync(srcDataPath, 'utf8');
            res.end(fileContent);
            console.log(`✅ 成功从${srcDataPath}提供building_data.js`);
          } else {
            // 如果文件不存在，返回404
            res.statusCode = 404;
            res.setHeader('Content-Type', 'text/plain');
            res.end('building_data.js not found');
            console.error(`❌ 文件不存在: ${srcDataPath}`);
          }
        } catch (error) {
          console.error('Error serving building_data.js:', error);
          res.statusCode = 500;
          res.setHeader('Content-Type', 'text/plain');
          res.end('Error serving building_data.js');
        }
      });
    },
    // 确保Vite可以访问src/data目录
    fs: {
      allow: ['..']
    },
    // 配置API代理
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    minify: 'esbuild',
    sourcemap: false
  }
})