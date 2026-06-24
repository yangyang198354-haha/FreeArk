/**
 * @module MOD-STORE-AUTH
 * @author sub_agent_software_developer
 * @description Pinia auth store. isAdmin uses role === 'admin' exclusively
 *   (NOT Django is_staff — per project admin auth convention).
 *   Hydrates from uni.storage on startup so token survives cold launch.
 */

import { defineStore } from 'pinia'
import { saveAuth, getToken, getUserInfo, clearAuth } from '@/utils/auth'

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
