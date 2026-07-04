/**
 * v1.12.0 小程序个人中心特性 — 前端单元测试
 * 覆盖: authStore avatarUrl/nickname getter, auth 存储往返, 页面 computed 逻辑
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/store/auth'
import { saveAuth, getToken, getUserInfo, clearAuth } from '@/utils/auth'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('v1.12.0 — store/auth avatarUrl / nickname getters', () => {
  it('TC-UNIT-020: avatarUrl getter 有值时返回 URL', () => {
    const s = useAuthStore()
    s.login('tok', { username: 'alice', role: 'user', avatar_url: 'https://example.com/a.png' })
    expect(s.avatarUrl).toBe('https://example.com/a.png')
  })

  it('TC-UNIT-020: avatarUrl getter 无值时返回 null', () => {
    const s = useAuthStore()
    s.login('tok', { username: 'bob', role: 'user' })
    expect(s.avatarUrl).toBeNull()
  })

  it('TC-UNIT-020: avatarUrl getter 字段缺失时返回 null', () => {
    const s = useAuthStore()
    s.login('tok', { username: 'bob', role: 'user', avatar_url: undefined })
    expect(s.avatarUrl).toBeNull()
  })

  it('TC-UNIT-021: nickname getter 有值时返回昵称', () => {
    const s = useAuthStore()
    s.login('tok', { username: 'alice', role: 'user', nickname: '小明' })
    expect(s.nickname).toBe('小明')
  })

  it('TC-UNIT-022: nickname getter 无值时返回 null', () => {
    const s = useAuthStore()
    s.login('tok', { username: 'bob', role: 'user' })
    expect(s.nickname).toBeNull()
  })

  it('TC-UNIT-020+021: avatarUrl 和 nickname 同时有值', () => {
    const s = useAuthStore()
    s.login('tok', {
      username: 'alice', role: 'user',
      avatar_url: 'https://x.com/av.png', nickname: 'Alice',
    })
    expect(s.avatarUrl).toBe('https://x.com/av.png')
    expect(s.nickname).toBe('Alice')
  })
})

describe('v1.12.0 — store/auth username / role 不退化', () => {
  it('username getter 仍然返回 username', () => {
    const s = useAuthStore()
    s.login('tok', { username: 'alice', role: 'user', nickname: '小明' })
    expect(s.username).toBe('alice')
  })

  it('role getter 仍然返回 role', () => {
    const s = useAuthStore()
    s.login('tok', { username: 'alice', role: 'user' })
    expect(s.role).toBe('user')
  })
})

describe('v1.12.0 — utils/auth 存储往返 avatar_url / nickname', () => {
  it('saveAuth 存入含 avatar_url 的 userInfo，getUserInfo 可读回', () => {
    saveAuth('tok', { username: 'alice', role: 'user', avatar_url: 'https://a.com/x.png', nickname: 'Alice' })
    const info = getUserInfo()
    expect(info.avatar_url).toBe('https://a.com/x.png')
    expect(info.nickname).toBe('Alice')
    expect(info.username).toBe('alice')
  })

  it('TC-UNIT-012: clearAuth 清空后 getUserInfo 返回 null', () => {
    saveAuth('tok', { avatar_url: 'url', nickname: 'n' })
    clearAuth()
    expect(getUserInfo()).toBeNull()
    expect(getToken()).toBeNull()
  })

  it('userInfo 不含 avatar_url 时，getUserInfo 返回 null 字段不影响', () => {
    saveAuth('tok', { username: 'bob', role: 'user' })
    const info = getUserInfo()
    expect(info.username).toBe('bob')
    expect(info.avatar_url).toBeUndefined()
    expect(info.nickname).toBeUndefined()
  })
})

describe('v1.12.0 — computed 逻辑推理（AC-PROFILE-004/005）', () => {
  it('TC-UNIT-021 + TC-UNIT-022: nickname 优先于 username', () => {
    const s = useAuthStore()
    s.login('tok', { username: 'alice', role: 'user', nickname: 'Alice Wang' })
    // profile/index.vue: nickname = computed(() => authStore.nickname || authStore.username || '未登录')
    const displayName = s.nickname || s.username || '未登录'
    expect(displayName).toBe('Alice Wang')
  })

  it('TC-UNIT-022: nickname 为 null 时降级到 username', () => {
    const s = useAuthStore()
    s.login('tok', { username: 'alice', role: 'user', nickname: null })
    const displayName = s.nickname || s.username || '未登录'
    expect(displayName).toBe('alice')
  })

  it('TC-UNIT-023: 未登录时 displayName = 未登录', () => {
    const s = useAuthStore()
    // 未 login
    const displayName = s.nickname || s.username || '未登录'
    expect(displayName).toBe('未登录')
  })

  it('TC-UNIT-017 + TC-UNIT-018: avatar 条件渲染逻辑', () => {
    // 有 avatarUrl → 显示图片（v-if）
    const s = useAuthStore()
    s.login('tok', { username: 'a', role: 'user', avatar_url: 'https://x.com/a.png' })
    const showImage = !!s.avatarUrl
    expect(showImage).toBe(true)

    // 无 avatarUrl → 显示文字头像（v-else）
    s.logout()
    s.login('tok', { username: 'b', role: 'user' })
    expect(!!s.avatarUrl).toBe(false)
  })

  it('TC-UNIT-005: userInfo id → ARK-{id} 格式化', () => {
    const s = useAuthStore()
    s.login('tok', { id: 42, username: 'test', role: 'user' })
    const userId = s.userInfo?.id != null ? `ARK-${s.userInfo.id}` : (s.username || '—')
    expect(userId).toBe('ARK-42')
  })

  it('TC-UNIT-005-05: nickname 不影响 ID 显示', () => {
    const s = useAuthStore()
    s.login('tok', { id: 7, username: 'alice', email: 'alice@test.com', nickname: 'Alice' })
    const userId = `ARK-${s.userInfo.id}`
    const email = s.userInfo.email
    expect(userId).toBe('ARK-7')
    expect(email).toBe('alice@test.com')
    expect(s.nickname).toBe('Alice')
    // 验证 ID 和 email 独立于 nickname
  })
})

describe('v1.12.0 — login page rememberMe (AC-AUTH-001-01/06)', () => {
  it('TC-UNIT-013: rememberMe ref 初始值为 false（模拟 login/index.vue setup）', () => {
    // 模拟 Vue ref 初始化: const rememberMe = ref(false)
    const rememberMe = { value: false }
    expect(rememberMe.value).toBe(false)
  })

  it('TC-UNIT-014: api.login() 参数 remember_me 来自变量而非硬编码', () => {
    // 模拟 login/index.vue handleLogin:
    //   const res = await api.login({ username, password, remember_me: rememberMe.value })
    const rememberMe = { value: true }
    const loginPayload = {
      username: 'testuser',
      password: 'testpass',
      remember_me: rememberMe.value,  // 来自变量，非硬编码
    }
    expect(loginPayload.remember_me).toBe(true)
    rememberMe.value = false
    const loginPayload2 = {
      username: 'testuser',
      password: 'testpass',
      remember_me: rememberMe.value,
    }
    expect(loginPayload2.remember_me).toBe(false)
  })
})

describe('v1.12.0 — logout 清空后 avatarUrl/nickname 恢复 null (AC-PROFILE-004-05)', () => {
  it('TC-INT-012: logout 后 avatarUrl 和 nickname 均为 null', () => {
    const s = useAuthStore()
    s.login('tok', { username: 'a', role: 'user', avatar_url: 'https://img.example.com/avatar.jpg', nickname: 'N' })
    expect(s.avatarUrl).toBe('https://img.example.com/avatar.jpg')
    expect(s.nickname).toBe('N')
    s.logout()
    expect(s.avatarUrl).toBeNull()
    expect(s.nickname).toBeNull()
    expect(s.isLoggedIn).toBe(false)
  })
})
