import { createApp } from 'vue'
import axios from 'axios'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'

// 导入全局样式
import './assets/global.css'

const app = createApp(App)

// 注册所有Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(router)
app.use(ElementPlus, { locale: zhCn })

// 配置axios基础URL
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL

// 添加错误处理逻辑，当环境变量未正确配置时提供明确的错误提示
if (!apiBaseUrl) {
  console.error('错误：环境变量VITE_API_BASE_URL未配置！请在.env文件中配置该环境变量。')
  console.error('示例配置：VITE_API_BASE_URL=http://localhost:8000')
  console.error('应用将使用默认值http://localhost:8000继续运行')
}

// 设置axios默认基础URL
axios.defaults.baseURL = apiBaseUrl || 'http://localhost:8000'

// 输出当前API基础URL配置
console.log('API基础URL配置：', axios.defaults.baseURL)

app.config.globalProperties.$axios = axios
app.mount('#app')