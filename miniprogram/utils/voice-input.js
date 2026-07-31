/**
 * @module MOD-VOICE-INPUT
 * @description 语音输入封装（v1.12.0 MOD-P1208 方案B / v1.5.2）
 *
 * 微信原生 RecorderManager 录音 → WAV 上传 → 后端 Sherpa-ONNX ASR。
 * fail-open：任何异常降级回退文本输入。
 *
 * 多端应用 APK 兼容（v1.5.1）：
 *   微信多端小程序打包 APK 后，运行时基于 MP-WEIXIN 代码，但已脱离微信权限体系，
 *   wx.getSetting / wx.authorize / wx.openSetting 不可用。
 *   必须改用 wx.getAppAuthorizeSetting / wx.openAppAuthorizeSetting。
 *   由于 #ifdef APP-PLUS 在 MP-WEIXIN 编译时会被剔除，这里用运行时判断
 *   wx.getAppAuthorizeSetting 是否存在来区分环境。
 *   参考: https://developers.weixin.qq.com/miniprogram/dev/platform-capabilities/miniapp/scene/dev/setting.html
 *
 * v1.5.2：
 *   - 修复 RecorderManager.onStop 只注册一次（追加改为单次绑定）：之前每次都用队列
 *   - 增加 DIAG 诊断日志：每步 console 定位 APK 链路断点
 *   - POST 请求失败时输出详细信息，避免全链路静默失败
 *
 * 用法：
 *   import { startRecording, stopAndRecognize } from '@/utils/voice-input'
 *   @touchstart="startRecording()"
 *   @touchend="stopAndRecognize().then(text => { if (text) send(text) })"
 */

import { BASE_URL } from './http'
import { getToken } from './auth'

// 诊断开关：输出详细链路日志（真机调试 / APK 排查定位用）
const DIAG = true

var _manager = null
var _recording = false
// onStop 回调队列：每次 stopAndRecognize 入队一次，onStop 触发时出队执行
var _onStopQueue = []
// 是否已注册 onStop（只注册一次，防止重复叠加）
var _onStopRegistered = false

/**
 * 运行时判断是否在多端应用 APK 中运行。
 * 多端 APK 中 wx.getAppAuthorizeSetting 函数存在且可用；
 * 普通微信小程序中该 API 不存在。
 */
function _isMultiTerminalApp() {
  return typeof wx !== 'undefined' && typeof wx.getAppAuthorizeSetting === 'function'
}

function _log(tag, msg, payload) {
  if (!DIAG) return
  if (payload === undefined) {
    console.log('[voice-input] ' + tag + ': ' + msg)
  } else {
    console.log('[voice-input] ' + tag + ': ' + msg, payload)
  }
}

/** 获取或创建 RecorderManager（单例）。 */
function _getManager() {
  if (_manager) return _manager
  _manager = uni.getRecorderManager()

  _manager.onError(function (res) {
    console.warn('[voice-input] 录音错误:', JSON.stringify(res))
    var msg = (res && (res.errMsg || res.message)) || '录音失败'

    // "stop record fail" 是 startRecording() 中清理残留录音的预期行为，
    // 此时录音尚未开始或已正常停止，不应重置 _recording 标志。
    if (msg.indexOf('stop record fail') !== -1) {
      uni.hideToast()
      return
    }

    // "audio is recording, don't start again" 表示上一次录音的原生层 stop
    // 尚未完成。主动停止残留录音机，提示用户重试。
    if (msg.indexOf("don't start") !== -1 || msg.indexOf('already') !== -1) {
      _recording = false
      uni.hideToast()
      uni.showToast({ title: '录音繁忙，请稍后重试', icon: 'none', duration: 2000 })
      try { _manager.stop() } catch (_) { /* ignore */ }
      return
    }

    _recording = false
    uni.hideToast()
    // 权限错误：引导用户去设置页打开
    if (msg.indexOf('auth') !== -1 || msg.indexOf('permission') !== -1 || msg.indexOf('deny') !== -1) {
      uni.showModal({
        title: '需要录音权限',
        content: '请在设置中开启麦克风权限，用于语音输入。',
        confirmText: '去设置',
        success: function (modalRes) {
          if (modalRes.confirm) {
            // #ifdef MP-WEIXIN
            if (_isMultiTerminalApp()) {
              // 多端应用 APK：跳系统权限设置页
              wx.openAppAuthorizeSetting({})
            } else {
              // 普通微信小程序：跳小程序权限设置页
              uni.openSetting({})
            }
            // #endif
          }
        },
      })
    } else {
      uni.showToast({ title: msg + '，请使用文字输入', icon: 'none', duration: 2000 })
    }
  })

  // onStop 只注册一次：出队执行队列中的回调
  _manager.onStop(function (res) {
    _log('onStop', '触发', res ? { tempFilePath: res.tempFilePath, fileSize: res.fileSize, duration: res.duration } : null)
    uni.hideToast()
    var cb = _onStopQueue.shift()
    if (cb) cb(res)
  })
  _onStopRegistered = true

  return _manager
}

/**
 * 检查并请求录音权限，返回 true=已授权。
 */
function _checkPermission() {
  // #ifdef MP-WEIXIN
  // 多端应用 APK：wx.getSetting / wx.authorize / wx.openSetting 不可用，
  // 改用 wx.getAppAuthorizeSetting 读 microphoneAuthorized 状态。
  // 'not determined' 时调用录音 start() 会自动弹系统权限请求，故与 'authorized' 一并放行。
  if (_isMultiTerminalApp()) {
    _log('权限检查', '多端 APK：调用 wx.getAppAuthorizeSetting')
    return new Promise(function (resolve) {
      wx.getAppAuthorizeSetting({
        success: function (res) {
          _log('权限检查', 'getAppAuthorizeSetting 成功', res)
          var state = res && res.microphoneAuthorized
          if (state === 'denied') {
            uni.showModal({
              title: '需要录音权限',
              content: '请在系统设置中开启麦克风权限后重试',
              confirmText: '去设置',
              success: function (modalRes) {
                if (modalRes.confirm) {
                  wx.openAppAuthorizeSetting({
                    success: function () { resolve(false) },
                    fail: function () { resolve(false) },
                  })
                } else {
                  resolve(false)
                }
              },
              fail: function () { resolve(false) },
            })
          } else {
            // 'authorized' 或 'not determined' 都放行
            resolve(true)
          }
        },
        fail: function (err) {
          _log('权限检查', 'getAppAuthorizeSetting 失败', err)
          resolve(false)
        },
      })
    })
  }

  // 普通微信小程序流程
  _log('权限检查', '微信小程序：调用 uni.getSetting')
  return new Promise(function (resolve) {
    uni.getSetting({
      success: function (res) {
        if (res.authSetting['scope.record'] === false) {
          // 用户之前拒绝过 → 弹窗引导去设置
          uni.showModal({
            title: '需要录音权限',
            content: '请在设置中开启麦克风权限后重试',
            confirmText: '去设置',
            success: function (modalRes) {
              if (modalRes.confirm) {
                uni.openSetting({})
              }
              resolve(false)
            },
            fail: function () { resolve(false) },
          })
        } else if (res.authSetting['scope.record'] === true) {
          resolve(true)
        } else {
          // 未请求过 → 首次申请
          uni.authorize({
            scope: 'scope.record',
            success: function () { resolve(true) },
            fail: function () {
              uni.showToast({ title: '录音权限未开启，请在设置中允许', icon: 'none', duration: 2000 })
              resolve(false)
            },
          })
        }
      },
      fail: function () { resolve(false) },
    })
  })
  // #endif
  // #ifndef MP-WEIXIN
  return Promise.resolve(true)
  // #endif
}

/**
 * 长按开始录音。
 */
export async function startRecording() {
  if (_recording) { _log('start', '忽略：_recording=true'); return }

  // ⚠️  Set _recording BEFORE await to close the double-tap race window.
  //     If permission check fails we reset it below.
  _recording = true

  var ok = await _checkPermission()
  if (!ok) { _recording = false; _log('start', '权限检查失败，退出'); return }

  var manager = _getManager()
  if (!manager) { _recording = false; return }

  uni.showToast({ title: '正在聆听…', icon: 'none', duration: 60000 })
  _log('start', '显示聆听 toast，start 录音')

  // Ensure any stale recording is stopped before starting a new one.
  // Previous onStop callback may not have fired yet, leaving the native
  // recorder in "recording" state → start() would throw.
  try { manager.stop() } catch (_) { /* ignore */ }

  try {
    manager.start({
      format: 'wav',
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      duration: 60000,
    })
    _log('start', 'manager.start() 调用成功')
  } catch (e) {
    _log('start', 'manager.start() 异常', e && e.message)
    uni.hideToast()
    _recording = false
    throw e
  }
}

/**
 * 松手停止录音并上传识别 → Promise<string|null>。
 */
export function stopAndRecognize() {
  return new Promise(function (resolve, reject) {
    _log('stopAndRecognize', '进入，_recording=' + _recording)
    if (!_recording) { resolve(null); return }
    _recording = false

    var manager = _getManager()
    if (!manager) { uni.hideToast(); resolve(null); return }

    var resolved = false
    function done(val) { if (resolved) return; resolved = true; clearTimeout(timer); resolve(val) }

    // onStop 回调入队（onStop 已在 _getManager 内统一注册，出队执行）
    _onStopQueue.push(function (res) {
      _log('stopAndRecognize', 'onStop 回调执行', res ? { tempFilePath: res.tempFilePath, fileSize: res.fileSize, duration: res.duration } : null)
      var tempFilePath = res && res.tempFilePath
      if (!tempFilePath) {
        uni.showToast({ title: '未录到语音，请重试', icon: 'none', duration: 1500 })
        done(null)
        return
      }
      _uploadAndRecognize(tempFilePath).then(done).catch(function () { done(null) })
    })

    // 超时兜底：onStop 3 秒未触发则报错（多端 APK 里 Media SDK 未生效时 onStop 不会触发）
    var timer = setTimeout(function () {
      _log('stopAndRecognize', '⚠️ onStop 3 秒未触发，超时兜底')
      // 出队未执行的回调
      _onStopQueue.pop()
      uni.hideToast()
      uni.showModal({
        title: '录音异常',
        content: _isMultiTerminalApp()
          ? '录音未正常结束。请确认 APK 是用最新的 project.miniapp.json（Media SDK 已开启）重新构建的；若已重新构建仍异常，请反馈此提示。'
          : '录音未正常结束，请重试或使用文字输入',
        showCancel: false,
        confirmText: '知道了',
      })
      done(null)
    }, 3000)

    try {
      manager.stop()
      _log('stopAndRecognize', 'manager.stop() 调用成功')
    } catch (e) {
      _log('stopAndRecognize', 'manager.stop() 异常', e && e.message)
      clearTimeout(timer)
      _onStopQueue.pop()
      uni.hideToast()
      done(null)
    }
  })
}

/** 上传 WAV → 后端 ASR → 文本（base64 编码，走 request 域名白名单） */
function _uploadAndRecognize(filePath) {
  _log('上传识别', '开始，filePath=' + filePath)
  return new Promise(function (resolve, reject) {
    uni.showToast({ title: '识别中…', icon: 'loading', duration: 15000 })

    // 读文件 → base64 → JSON POST（绕过 uploadFile 域名白名单限制）
    // 多端应用（微信小程序 + APK）统一用 uni.getFileSystemManager 读文件转 base64
    // #ifdef MP-WEIXIN
    var fs = uni.getFileSystemManager()
    var base64
    try {
      base64 = fs.readFileSync(filePath, 'base64')
      _log('上传识别', 'readFileSync 成功，base64 长度=' + (base64 && base64.length))
    } catch (e) {
      _log('上传识别', 'readFileSync 失败', e && e.message)
      uni.hideToast()
      uni.showToast({ title: '读取录音文件失败，请使用文字输入', icon: 'none', duration: 2000 })
      reject(new Error('read failed'))
      return
    }
    if (!base64) {
      _log('上传识别', 'base64 为空')
      uni.hideToast()
      uni.showToast({ title: '录音数据异常，请重试', icon: 'none', duration: 2000 })
      reject(new Error('empty base64'))
      return
    }
    _postAudioBase64(base64, resolve, reject)
    // #endif

    // #ifndef MP-WEIXIN
    uni.hideToast()
    uni.showToast({ title: '语音识别暂不可用，请使用文字输入', icon: 'none', duration: 2000 })
    reject(new Error('not supported'))
    // #endif
  })
}

/** 将 base64 音频 POST 到后端 ASR 接口 */
function _postAudioBase64(base64, resolve, reject) {
  var token = getToken()
  var url = BASE_URL + '/api/miniapp/voice/recognize/'
  _log('POST', '请求 ' + url + '，token=' + (token ? '有' : '无') + '，base64 长度=' + base64.length)
  uni.request({
    url: url,
    method: 'POST',
    header: {
      'content-type': 'application/json',
      'Authorization': token ? 'Token ' + token : '',
    },
    data: JSON.stringify({ audio_base64: base64, format: 'wav' }),
    success: function (res) {
      _log('POST', '成功，status=' + res.statusCode + ' data=' + JSON.stringify(res.data || null))
      uni.hideToast()
      var text = (res.data && res.data.text || '').trim()
      if (text) { _log('POST', '识别结果：' + text); resolve(text) }
      else {
        uni.showToast({ title: '未识别到内容，请重试', icon: 'none', duration: 2000 })
        reject(new Error('empty'))
      }
    },
    fail: function (err) {
      _log('POST', '失败', err)
      uni.hideToast()
      // 多端 APK 中 request 失败常见原因：证书不完整 / 自签名证书。
      // 若 errMsg 含 "certificate" 时提示用户证书问题。
      var msg = (err && err.errMsg) || ''
      var userTip = '语音识别暂不可用，请使用文字输入'
      if (msg.indexOf('certificate') !== -1 || msg.indexOf('ssl') !== -1 || msg.indexOf('SSL') !== -1) {
        userTip = '服务器证书问题，请联系管理员'
      } else if (msg.indexOf('timeout') !== -1) {
        userTip = '网络超时，请检查网络'
      } else if (msg.indexOf('fail') !== -1) {
        userTip = '请求失败：' + msg.substring(0, 30)
      }
      uni.showToast({ title: userTip, icon: 'none', duration: 2500 })
      reject(new Error('request failed: ' + msg))
    },
  })
}
