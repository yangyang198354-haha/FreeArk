/**
 * @module MOD-STORE-AUTH
 * @author sub_agent_software_developer
 * @description Pinia auth store. isAdmin uses role === 'admin' exclusively
 *   (NOT Django is_staff — per project admin auth convention).
 *   Hydrates from uni.storage on startup so token survives cold launch.
 */

import { defineStore } from 'pinia'
import { saveAuth, getToken, getUserInfo, clearAuth } from '@/utils/auth'
import { BASE_URL } from '@/utils/http'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getToken(),
    userInfo: getUserInfo(),
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
    // Admin check: role === 'admin' only. DO NOT use is_staff (not returned by /api/auth/me/).
    isAdmin: (state) => state.userInfo?.role === 'admin',
    username: (state) => state.userInfo?.username || '',
    role: (state) => state.userInfo?.role || '',
    // v1.12.0: 头像URL和昵称（来自后端登录响应，为null时前端降级展示）
    //   后端返回的 avatar_url 可能是相对路径（/media/avatars/xxx.jpg），
    //   <image> 组件需要绝对 URL，相对路径会被小程序解析为 localhost。
    avatarUrl: (state) => {
      const url = state.userInfo?.avatar_url
      if (!url) return null
      if (url.startsWith('http://') || url.startsWith('https://')) return url
      return BASE_URL + url
    },
    nickname: (state) => state.userInfo?.nickname || null,
  },
  actions: {
    // token and userInfo come from POST /api/auth/login/ response:
    //   res.token  and  res.user  (NOT res.user_info)
    login(token, userInfo) {
      this.token = token
      this.userInfo = userInfo
      saveAuth(token, userInfo)
    },
    logout() {
      this.token = null
      this.userInfo = null
      clearAuth()
    },
  },
})
