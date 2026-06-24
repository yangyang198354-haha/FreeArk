/**
 * @module MOD-HTTP
 * @author sub_agent_software_developer
 * @description Centralised HTTP client. All requests go through this module.
 *   BASE_URL: change to production HTTPS domain before release.
 *   [INF-1] No credentials hardcoded — only the API host. DB connections live in backend env vars.
 *   [INF-2] No Docker/container dependencies.
 */

import { getToken, clearAuth } from './auth'

// Development: change this to your local backend IP
// Production: change this to your HTTPS domain
const BASE_URL = 'http://192.168.31.51:8000'

export const WS_BASE_URL = 'ws://192.168.31.51:8000'

let _sessionExpiredShown = false

function request(method, path, data, extraHeaders = {}) {
  const token = getToken()
  if (!token && path !== '/api/auth/login/') {
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
