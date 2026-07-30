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

  // #ifdef APP-PLUS
  // APP 端：使用 plus.android 权限检查（仅 Android）
  return new Promise((resolve) => {
    if (plus.os && plus.os.name === 'Android') {
      const perms = {
        'scope.record': 'android.permission.RECORD_AUDIO',
        'scope.camera': 'android.permission.CAMERA',
      }
      const perm = perms[scope]
      if (!perm) {
        // 未知 scope，APP 端默认放行（由 uni.chooseImage 等内部 API 自行处理）
        resolve('authorized')
        return
      }
      const main = plus.android.runtimeMainActivity()
      if (!main) { resolve('authorized'); return }
      try {
        // Android 6.0+ 运行时权限
        if (plus.os.version && parseInt(plus.os.version, 10) >= 6) {
          const granted = plus.android.invoke(main, 'checkSelfPermission', perm)
          if (granted === 0) {
            resolve('authorized')
          } else {
            // 请求权限
            plus.android.requestPermissions(
              [perm],
              function (e) {
                const result = e.granted && e.granted.length > 0
                resolve(result ? 'authorized' : 'denied')
              },
              function () { resolve('denied') }
            )
          }
        } else {
          // Android 6.0 以下，安装时已授权
          resolve('authorized')
        }
      } catch (e) {
        resolve('denied')
      }
    } else {
      // iOS 或其他平台，默认放行
      resolve('authorized')
    }
  })
  // #endif

  // #ifndef MP-WEIXIN || APP-PLUS
  // Non-WeChat environment -- permissions not applicable, always report as authorized
  return Promise.resolve('authorized')
  // #endif
}

export default { requestPermission }
