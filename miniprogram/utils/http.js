/**
 * @module MOD-HTTP
 * @author sub_agent_software_developer
 * @description Centralised HTTP client. All requests go through this module.
 *   BASE_URL: change to production HTTPS domain before release.
 *   [INF-1] No credentials hardcoded — only the API host. DB connections live in backend env vars.
 *   [INF-2] No Docker/container dependencies.
 */

import { getToken, clearAuth } from './auth'
import { useAuthStore } from '@/store/auth'

// Development: change this to your local backend IP
// Production: 已备案域名，VPS nginx(443/Let's Encrypt) 终止 TLS → frp 隧道 → Pi nginx:8080
export const BASE_URL = 'https://ai-freeark.xin'

export const WS_BASE_URL = 'wss://ai-freeark.xin'

let _sessionExpiredShown = false

// 无需登录即可访问的公开端点前缀（v1.8.0：小程序注册/微信一键登录在拿到 token 之前调用）。
// 命中这些前缀时不强制跳登录页，让请求带空 token 正常发出。
const PUBLIC_PREFIXES = ['/api/auth/login/', '/api/miniapp/auth/']

function request(method, path, data, extraHeaders = {}) {
  const token = getToken()
  const isPublic = PUBLIC_PREFIXES.some((p) => path.startsWith(p))
  if (!token && !isPublic) {
    uni.reLaunch({ url: '/pages/login/index' })
    return Promise.reject(new Error('NOT_LOGGED_IN'))
  }

  const headers = {
    'Content-Type': 'application/json',
    ...extraHeaders,
  }
  if (token) {
    headers['Authorization'] = `Token ${token}`
  }

  return new Promise((resolve, reject) => {
    uni.request({
      url: `${BASE_URL}${path}`,
      method,
      data,
      header: headers,
      timeout: 15000,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else if (res.statusCode === 401) {
          handleUnauthorized()
          reject(new Error('SESSION_EXPIRED'))
        } else {
          reject(new Error(`HTTP ${res.statusCode}`))
        }
      },
      fail(err) {
        reject(new Error(`网络错误: ${err.errMsg}`))
      }
    })
  })
}

function handleUnauthorized() {
  clearAuth()
  // 同时清空 Pinia store 内存中的 token，否则登录页检查 isLoggedIn 仍为 true，
  // 会立即 reLaunch 回首页，形成 401→登录页→首页→401 的死循环闪屏
  try { useAuthStore().logout() } catch (e) { /* store 可能未初始化 */ }
  if (!_sessionExpiredShown) {
    _sessionExpiredShown = true
    uni.showToast({ title: '会话已过期，请重新登录', icon: 'none', duration: 2000 })
    setTimeout(() => {
      _sessionExpiredShown = false
      uni.reLaunch({ url: '/pages/login/index' })
    }, 2000)
  }
}

function buildQuery(params) {
  if (!params || Object.keys(params).length === 0) return ''
  return '?' + Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&')
}

export const http = {
  get: (path, params) => request('GET', path + buildQuery(params)),
  post: (path, data) => request('POST', path, data),
  put: (path, data) => request('PUT', path, data),
  patch: (path, data) => request('PATCH', path, data),
  del: (path) => request('DELETE', path),
}

export default http
