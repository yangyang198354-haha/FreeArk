import axios from 'axios'

// 创建axios实例
// 从环境变量获取基础URL，确保不包含/api前缀
const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const api = axios.create({
  baseURL: `${baseURL}/api`,
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

// 用户管理相关API
export const userApi = {
  // 获取用户列表
  getUsers: (params) => api.get('/users/', { params }),
  // 获取单个用户信息
  getUser: (id) => api.get(`/users/${id}/`),
  // 创建用户
  createUser: (userData) => api.post('/users/', userData),
  // 更新用户
  updateUser: (id, userData) => api.put(`/users/${id}/`, userData),
  // 删除用户
  deleteUser: (id) => api.delete(`/users/${id}/`)
}

// 能耗报表相关API
export const usageApi = {
  // 查询日用量报表
  getDailyUsage: (params) => api.get('/usage/daily/', { params }),
  // 查询月用量报表
  getMonthlyUsage: (params) => api.get('/usage/quantity/monthly/', { params }),
  // 查询用量查询数据
  getUsageQuery: (params) => api.get('/usage/quantity/specifictimeperiod/', { params })
}

export default api