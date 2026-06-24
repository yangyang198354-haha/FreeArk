/**
 * @module MOD-AUTH-UTIL
 * @author sub_agent_software_developer
 * @description Auth token and userInfo storage helpers (uni.storage wrappers)
 */

const TOKEN_KEY = 'userToken'
const USER_INFO_KEY = 'userInfo'

export function saveAuth(token, userInfo) {
  uni.setStorageSync(TOKEN_KEY, token)
  uni.setStorageSync(USER_INFO_KEY, JSON.stringify(userInfo))
}

export function getToken() {
  return uni.getStorageSync(TOKEN_KEY) || null
}

export function getUserInfo() {
  const raw = uni.getStorageSync(USER_INFO_KEY)
  try { return raw ? JSON.parse(raw) : null } catch { return null }
}

export function isAdmin() {
  const info = getUserInfo()
  return info?.role === 'admin'
}

export function clearAuth() {
  uni.removeStorageSync(TOKEN_KEY)
  uni.removeStorageSync(USER_INFO_KEY)
}
