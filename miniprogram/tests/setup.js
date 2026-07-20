/**
 * Vitest 全局环境：mock 小程序全局 `uni`，使纯逻辑模块可在 Node 下测试。
 * storage 用内存 Map 实现（auth 往返可测）；其余 API 为 vi.fn，测试内可按需 mockImplementation。
 * 每个用例前清空 storage 并重置 mock。
 */
import { vi, beforeEach } from 'vitest'

const storage = new Map()

globalThis.uni = {
  // storage（同步）
  setStorageSync: (k, v) => { storage.set(k, v) },
  getStorageSync: (k) => (storage.has(k) ? storage.get(k) : ''),
  removeStorageSync: (k) => { storage.delete(k) },
  // 交互/导航（占位，可断言被调用）
  showToast: vi.fn(),
  showModal: vi.fn(),
  reLaunch: vi.fn(),
  navigateTo: vi.fn(),
  navigateBack: vi.fn(),
  switchTab: vi.fn(),
  setNavigationBarTitle: vi.fn(),
  hideKeyboard: vi.fn(),
  // 网络（测试内覆盖 implementation）
  request: vi.fn(),
  connectSocket: vi.fn(),
  uploadFile: vi.fn(),
  chooseImage: vi.fn(),
  // 图表用（组件未在此层测试，占位即可）
  getSystemInfoSync: vi.fn(() => ({ pixelRatio: 2, windowWidth: 375 })),
  createSelectorQuery: vi.fn(() => ({
    in: () => ({ select: () => ({ fields: () => ({ exec: () => {} }) }) }),
  })),
}

// wx global mock for permission.js (uses wx.getSetting, wx.authorize, wx.openSetting)
globalThis.wx = {
  getSetting: vi.fn(),
  authorize: vi.fn(),
  openSetting: vi.fn(),
}

// 暴露给个别用例直接操作内存 storage
globalThis.__resetStorage = () => storage.clear()

beforeEach(() => {
  storage.clear()
  vi.clearAllMocks()
})
