import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { copyFileSync, existsSync, mkdirSync } from 'fs'
import { resolve, join, dirname } from 'path'

// 自定义插件：在构建完成后复制静态资源文件
function copyStaticFilesPlugin(buildDir) {
  return {
    name: 'copy-static-files',
    closeBundle() {
      // 定义需要复制的文件列表
      const filesToCopy = [
        { src: join(__dirname, 'src', 'data', 'building_data.js'), dest: join(__dirname, buildDir, 'building_data.js') },
        { src: join(__dirname, 'home.html'), dest: join(__dirname, buildDir, 'home.html') },
        { src: join(__dirname, 'home.css'), dest: join(__dirname, buildDir, 'home.css') },
        { src: join(__dirname, 'favicon.png'), dest: join(__dirname, buildDir, 'favicon.png') },
        { src: join(__dirname, 'config.js'), dest: join(__dirname, buildDir, 'config.js') }
      ]
      
      // 确保构建目录存在
      const distDir = join(__dirname, buildDir)
      if (!existsSync(distDir)) {
        try {
          mkdirSync(distDir, { recursive: true })
          console.log(`✅ 创建构建目录: ${distDir}`)
        } catch (error) {
          console.error(`❌ 创建构建目录失败: ${error.message}`)
        }
      }
      
      // 复制每个文件
      filesToCopy.forEach(file => {
        if (existsSync(file.src)) {
          try {
            copyFileSync(file.src, file.dest)
            console.log(`✅ 成功从${file.src}复制到${file.dest}`)
          } catch (error) {
            console.error(`❌ 从${file.src}复制到${file.dest}失败: ${error.message}`)
            console.warn(`⚠️  复制文件失败，但构建过程将继续`)
          }
        } else {
          console.warn(`⚠️  源文件不存在: ${file.src}`)
          console.warn(`⚠️  无法复制文件，但构建过程将继续`)
        }
      })
    }
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 加载环境变量
  const env = loadEnv(mode, process.cwd())
  
  // 获取构建目录，默认为'dist'
  const buildDir = env.VITE_BUILD_DIR || 'dist'
  
  return {
  plugins: [
    vue(),
    copyStaticFilesPlugin(buildDir) // 添加自定义复制插件，传入构建目录
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
    outDir: buildDir,
    assetsDir: 'assets',
    minify: 'esbuild',
    sourcemap: false,
    // 修复Vite 6.0处理内联CSS的问题
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        manualChunks: undefined
      }
    }
  },
  // 优化HTML处理
  optimizeDeps: {
    esbuildOptions: {
      minifyIdentifiers: false
    }
  }
  }
})