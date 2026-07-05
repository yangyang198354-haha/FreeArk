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
 * Usage:
 *   import { requestPermission } from '@/utils/permission'
 *   const result = await requestPermission('scope.record', { name: '录音' })
 *   if (result === 'authorized') { /* proceed * / }
 */

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
  return new Promise((resolve) => {
    wx.getSetting({
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
                wx.openSetting({
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
        wx.authorize({
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
                  wx.openSetting({
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
