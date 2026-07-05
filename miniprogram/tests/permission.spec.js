/**
 * Unit tests for MOD-004: PermissionManager (miniprogram/utils/permission.js)
 * TC-UNIT-001 ~ TC-UNIT-006
 *
 * Covers: requestPermission(scope, options) all branches
 *   - Already authorized
 *   - First-time authorize (success + fail)
 *   - Previously denied (direct showModal, skip authorize)
 *   - getSetting failure
 *   - User cancels guide modal
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { requestPermission } from '@/utils/permission'

describe('utils/permission — requestPermission 分支覆盖', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ========================================================================
  // TC-UNIT-001: Already authorized (scope=true) → return 'authorized'
  // ========================================================================
  it('TC-UNIT-001: 已授权(scope=true) → 直接返回 authorized', async () => {
    wx.getSetting.mockImplementation(({ success }) => {
      success({ authSetting: { 'scope.record': true } })
    })

    const result = await requestPermission('scope.record', { name: '录音' })

    expect(result).toBe('authorized')
    expect(wx.getSetting).toHaveBeenCalled()
    expect(wx.authorize).not.toHaveBeenCalled()
  })

  // ========================================================================
  // TC-UNIT-002: First-time — authorize success → 'authorized'
  // ========================================================================
  it('TC-UNIT-002: 首次未授权 → authorize 成功 → 返回 authorized', async () => {
    wx.getSetting.mockImplementation(({ success }) => {
      success({ authSetting: {} }) // scope key not present = not yet asked
    })
    wx.authorize.mockImplementation(({ success }) => {
      success()
    })

    const result = await requestPermission('scope.record', { name: '录音' })

    expect(result).toBe('authorized')
    expect(wx.authorize).toHaveBeenCalledWith(
      expect.objectContaining({ scope: 'scope.record' })
    )
  })

  // ========================================================================
  // TC-UNIT-003: First-time authorize fail → showModal → openSetting → authorized
  // ========================================================================
  it('TC-UNIT-003: 首次授权失败 → showModal去设置 → 开户成功 → authorized', async () => {
    wx.getSetting.mockImplementation(({ success }) => {
      success({ authSetting: {} })
    })
    wx.authorize.mockImplementation(({ fail }) => {
      fail()
    })
    uni.showModal.mockImplementation(({ success }) => {
      success({ confirm: true }) // user clicked "去设置"
    })
    wx.openSetting.mockImplementation(({ success }) => {
      success({ authSetting: { 'scope.record': true } })
    })

    const result = await requestPermission('scope.record', { name: '录音' })

    expect(result).toBe('authorized')
    expect(uni.showModal).toHaveBeenCalled()
    expect(wx.openSetting).toHaveBeenCalled()
  })

  // ========================================================================
  // TC-UNIT-004: Previously denied (scope=false) → showModal directly
  //              (must NOT call authorize — WeChat rejects it silently)
  // ========================================================================
  it('TC-UNIT-004: 之前拒绝过(scope=false) → 直接showModal(不调authorize)', async () => {
    wx.getSetting.mockImplementation(({ success }) => {
      success({ authSetting: { 'scope.record': false } })
    })
    uni.showModal.mockImplementation(({ success }) => {
      success({ confirm: true })
    })
    wx.openSetting.mockImplementation(({ success }) => {
      success({ authSetting: { 'scope.record': true } })
    })

    const result = await requestPermission('scope.record', { name: '录音' })

    expect(result).toBe('authorized')
    expect(wx.authorize).not.toHaveBeenCalled()
    expect(uni.showModal).toHaveBeenCalled()
    expect(wx.openSetting).toHaveBeenCalled()
  })

  // ========================================================================
  // TC-UNIT-005: Previously denied → showModal → user clicks "取消" → 'cancelled'
  // ========================================================================
  it('TC-UNIT-005: 之前拒绝 → showModal点击取消 → 返回 cancelled', async () => {
    wx.getSetting.mockImplementation(({ success }) => {
      success({ authSetting: { 'scope.record': false } })
    })
    uni.showModal.mockImplementation(({ success }) => {
      success({ confirm: false }) // user cancelled
    })

    const result = await requestPermission('scope.record', { name: '录音' })

    expect(result).toBe('cancelled')
    expect(wx.openSetting).not.toHaveBeenCalled()
  })

  // ========================================================================
  // TC-UNIT-006: getSetting itself fails → showToast + return 'denied'
  // ========================================================================
  it('TC-UNIT-006: getSetting自身失败 → showToast + 返回 denied', async () => {
    wx.getSetting.mockImplementation(({ fail }) => {
      fail()
    })

    const result = await requestPermission('scope.record', { name: '录音' })

    expect(result).toBe('denied')
    expect(uni.showToast).toHaveBeenCalledWith(
      expect.objectContaining({ title: '无法获取权限状态，请稍后重试' })
    )
  })

  // ========================================================================
  // Bonus: First-time authorize fail → showModal → openSetting still denied
  // ========================================================================
  it('首次授权失败 → 去设置但用户仍未开户 → denied', async () => {
    wx.getSetting.mockImplementation(({ success }) => {
      success({ authSetting: {} })
    })
    wx.authorize.mockImplementation(({ fail }) => {
      fail()
    })
    uni.showModal.mockImplementation(({ success }) => {
      success({ confirm: true })
    })
    wx.openSetting.mockImplementation(({ success }) => {
      success({ authSetting: { 'scope.record': false } }) // still denied after settings
    })

    const result = await requestPermission('scope.record', { name: '录音' })

    expect(result).toBe('denied')
  })

  // ========================================================================
  // Bonus: Previously denied → showModal → openSetting fail
  // ========================================================================
  it('之前拒绝 → openSetting失败 → denied', async () => {
    wx.getSetting.mockImplementation(({ success }) => {
      success({ authSetting: { 'scope.record': false } })
    })
    uni.showModal.mockImplementation(({ success }) => {
      success({ confirm: true })
    })
    wx.openSetting.mockImplementation(({ fail }) => {
      fail()
    })

    const result = await requestPermission('scope.record', { name: '录音' })

    expect(result).toBe('denied')
  })

  // ========================================================================
  // Bonus: Previously denied → showModal itself fails
  // ========================================================================
  it('之前拒绝 → showModal失败 → denied', async () => {
    wx.getSetting.mockImplementation(({ success }) => {
      success({ authSetting: { 'scope.record': false } })
    })
    uni.showModal.mockImplementation(({ fail }) => {
      fail()
    })

    const result = await requestPermission('scope.record', { name: '录音' })

    expect(result).toBe('denied')
  })
})
