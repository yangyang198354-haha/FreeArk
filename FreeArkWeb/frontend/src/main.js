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

// API 请求统一由 src/utils/api.js 的 fetch 封装处理，使用 window.location.origin 作为 base。
// axios 仅保留作可选的全局实例，不再设置硬编码的 baseURL fallback。
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== 'undefined' ? window.location.origin : '');
if (apiBaseUrl) {
  axios.defaults.baseURL = apiBaseUrl;
}
console.log('API基础URL配置：', apiBaseUrl || '(使用 window.location.origin 动态解析)')

app.config.globalProperties.$axios = axios
app.mount('#app')