/**
 * @module MOD-004
 * @implements IFC-004-01
 * @author sub_agent_software_developer
 * @description Unified WeChat Mini Program permission manager (ADR-006).
 *   Handles scope.record (recording), scope.camera (camera), and album permissions.
 *
 *   Camera/album permissions are auto-requested by uni.chooseImage internally,
 *   so PermissionManager mainly handles recording permission and post-rejection
 *   guidance for all three permission types.
 *
 *   多端应用 APK 兼容（v1.5.1）：
 *   微信多端小程序打包 APK 后，运行时基于 MP-WEIXIN 代码，但已脱离微信权限体系，
 *   wx.getSetting / wx.authorize / wx.openSetting 不可用。
 *   必须改用 wx.getAppAuthorizeSetting / wx.openAppAuthorizeSetting。
 *   由于 #ifdef APP-PLUS 在 MP-WEIXIN 编译时会被剔除，这里用运行时判断
 *   wx.getAppAuthorizeSetting 是否存在来区分环境。
 *   参考: https://developers.weixin.qq.com/miniprogram/dev/platform-capabilities/miniapp/scene/dev/setting.html
 *
 * Usage:
 *   import { requestPermission } from '@/utils/permission'
 *   const result = await requestPermission('scope.record', { name: '录音' })
 *   if (result === 'authorized') { /* proceed * / }
 */

/**
 * 运行时判断是否在多端应用 APK 中运行。
 * 多端 APK 中 wx.getAppAuthorizeSetting 函数存在且可用；
 * 普通微信小程序中该 API 不存在。
 */
function _isMultiTerminalApp() {
  return typeof wx !== 'undefined' && typeof wx.getAppAuthorizeSetting === 'function'
}

/**
 * 多端应用 scope → getAppAuthorizeSetting 返回字段映射。
 */
const _scopeToAppField = {
  'scope.record': 'microphoneAuthorized',
  'scope.camera': 'cameraAuthorized',
}

/**
 * 多端应用 APK 环境下的权限请求流程。
 * @returns {Promise<'authorized'|'denied'|'cancelled'>}
 */
function _requestPermissionInApp(scope, guideTitle, guideContent) {
  const field = _scopeToAppField[scope]
  if (!field) {
    // 未知 scope，APP 端默认放行（由 uni.chooseImage 等内部 API 自行处理）
    return Promise.resolve('authorized')
  }
  return new Promise((resolve) => {
    wx.getAppAuthorizeSetting({
      success: (res) => {
        const state = res[field] // 'authorized' | 'denied' | 'not determined'
        if (state === 'denied') {
          // 用户已拒绝 → 引导去系统设置页
          uni.showModal({
            title: guideTitle,
            content: guideContent,
            confirmText: '去设置',
            cancelText: '取消',
            success: (modalRes) => {
              if (modalRes.confirm) {
                wx.openAppAuthorizeSetting({
                  // 设置页返回后无法立即知道用户是否开启，保守返回 denied，
                  // 用户再次点击麦克风会重新走 getAppAuthorizeSetting 检查
                  success: () => resolve('denied'),
                  fail: () => resolve('denied'),
                })
              } else {
                resolve('cancelled')
              }
            },
            fail: () => resolve('denied'),
          })
        } else {
          // 'authorized' 或 'not determined' 都放行
          // 'not determined' 时调用录音 start() 会自动弹系统权限请求
          resolve('authorized')
        }
      },
      fail: () => {
        uni.showToast({ title: '无法获取权限状态，请稍后重试', icon: 'none', duration: 2000 })
        resolve('denied')
      },
    })
  })
}

/**
 * Request a WeChat Mini Program permission.
 *
 * @param {string} scope - Permission scope, e.g. 'scope.record', 'scope.camera'
 * @param {object} options - Configuration options
 * @param {string} options.name - Human-readable permission name for prompts (e.g. '录音', '相机')
 * @param {string} [options.guideTitle] - Custom title for the settings guide modal
 * @param {string} [options.guideContent] - Custom content for the settings guide modal
 * @returns {Promise<'authorized'|'denied'|'cancelled'>}
 *   - 'authorized': Permission granted, proceed with the operation
 *   - 'denied': User denied and did not open settings
 *   - 'cancelled': User cancelled the settings guide modal
 */
export function requestPermission(scope, options = {}) {
  const name = options.name || '此功能'
  const guideTitle = options.guideTitle || '需要' + name + '权限'
  const guideContent = options.guideContent || '需要' + name + '权限才能使用此功能，请在设置中开启'

  // #ifdef MP-WEIXIN
  // 多端应用 APK 运行时也是 MP-WEIXIN 编译产物，需运行时判断
  if (_isMultiTerminalApp()) {
    return _requestPermissionInApp(scope, guideTitle, guideContent)
  }

  // 普通微信小程序流程
  return new Promise((resolve) => {
    uni.getSetting({
      success: (res) => {
        const auth = res.authSetting

        // Already authorized -- nothing to do
        if (auth[scope] === true) {
          resolve('authorized')
          return
        }

        // Previously denied -- cannot call authorize() again, must guide to settings
        if (auth[scope] === false) {
          uni.showModal({
            title: guideTitle,
            content: guideContent,
            confirmText: '去设置',
            cancelText: '取消',
            success: (modalRes) => {
              if (modalRes.confirm) {
                uni.openSetting({
                  success: (settingRes) => {
                    if (settingRes.authSetting[scope] === true) {
                      resolve('authorized')
                    } else {
                      resolve('denied')
                    }
                  },
                  fail: () => {
                    resolve('denied')
                  }
                })
              } else {
                resolve('cancelled')
              }
            },
            fail: () => {
              resolve('denied')
            }
          })
          return
        }

        // Never asked -- request for the first time
        uni.authorize({
          scope: scope,
          success: () => {
            resolve('authorized')
          },
          fail: () => {
            // User denied the first-time authorization -- show guide modal
            uni.showModal({
              title: guideTitle,
              content: guideContent,
              confirmText: '去设置',
              cancelText: '取消',
              success: (modalRes) => {
                if (modalRes.confirm) {
                  uni.openSetting({
                    success: (settingRes) => {
                      if (settingRes.authSetting[scope] === true) {
                        resolve('authorized')
                      } else {
                        resolve('denied')
                      }
                    },
                    fail: () => {
                      resolve('denied')
                    }
                  })
                } else {
                  resolve('cancelled')
                }
              },
              fail: () => {
                resolve('denied')
              }
            })
          }
        })
      },
      fail: () => {
        // getSetting itself failed -- cannot determine permission state
        uni.showToast({ title: '无法获取权限状态，请稍后重试', icon: 'none', duration: 2000 })
        resolve('denied')
      }
    })
  })
  // #endif

  // #ifndef MP-WEIXIN
  // Non-WeChat environment -- permissions not applicable, always report as authorized
  return Promise.resolve('authorized')
  // #endif
}

export default { requestPermission }
