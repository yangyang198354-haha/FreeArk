import axios from 'axios'

// 创建axios实例
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器 - 添加认证token
api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('userToken')
    if (token) {
      config.headers.Authorization = `Token ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器 - 处理认证错误
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response && error.response.status === 401) {
      // 清除token并跳转到登录页
      localStorage.removeItem('userToken')
      localStorage.removeItem('userInfo')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// 认证相关API
export const authApi = {
  // 登录
  login: (credentials) => api.post('/auth/login/', credentials),
  // 登出
  logout: () => api.post('/auth/logout/'),
  // 获取当前用户信息
  getCurrentUser: () => api.get('/auth/me/')
}

// 只保留认证相关API

export default api