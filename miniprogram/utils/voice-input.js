/**
 * @module MOD-VOICE-INPUT
 * @description 语音输入封装（v1.12.0 MOD-P1208 方案B）
 *
 * 微信原生 RecorderManager 录音 → WAV 上传 → 后端 Sherpa-ONNX ASR。
 * fail-open：任何异常降级回退文本输入。
 *
 * 用法：
 *   import { startRecording, stopAndRecognize } from '@/utils/voice-input'
 *   @touchstart="startRecording()"
 *   @touchend="stopAndRecognize().then(text => { if (text) send(text) })"
 */

import { BASE_URL } from './http'
import { getToken } from './auth'

var _manager = null
// 状态机：idle → starting → recording → stopping → idle
// - starting：manager.start() 已调用，等待 onStart 回调确认原生层真正开始录音
// - stopping：manager.stop() 已调用，等待 onStop 回调返回录音文件
// iOS 上 start()/stop() 的 onStart/onStop 回调延迟明显（WKWebView 音频会话初始化慢），
// 没有 starting/stopping 中间态会导致：
//   - starting 期间松手调 stop() → "recorder not start"
//   - stopping 期间再次 start() → "is recording or paused"
var _state = 'idle'
var _onStateChange = null

/**
 * 设置状态变化回调。供 ChatInputBar 等 UI 组件在「录音真的启动时」点亮按钮动画，
 * 避免 iOS 上 start()/onStart() 延迟导致 UI 与原生层录音状态不同步。
 * @param {(state: 'idle'|'starting'|'recording'|'stopping') => void} cb
 */
export function setStateChangeCallback(cb) {
  _onStateChange = typeof cb === 'function' ? cb : null
}

function _setState(next) {
  if (_state === next) return
  _state = next
  try { if (_onStateChange) _onStateChange(next) } catch (_) {}
}

/** 获取或创建 RecorderManager（单例）。 */
function _getManager() {
  if (_manager) return _manager
  _manager = uni.getRecorderManager()

  _manager.onStart(function () {
    _setState('recording')
  })

  _manager.onError(function (res) {
    console.warn('[voice-input] 录音错误:', JSON.stringify(res))
    var msg = (res && (res.errMsg || res.message)) || '录音失败'

    // 以下三类都是状态机要静默处理的边界情况，不弹 toast 干扰用户：
    // - "recorder not start"：iOS 上 start() 的 onStart 未回调时就 stop()
    // - "is recording or paused"：上次 onStop 未回调时就 start()
    // - "stop record fail"：startRecording() 中清理残留录音的预期行为
    if (msg.indexOf('recorder not start') !== -1 ||
        msg.indexOf('is recording or paused') !== -1 ||
        msg.indexOf('stop record fail') !== -1) {
      _setState('idle')
      uni.hideToast()
      return
    }

    // "audio is recording, don't start again" 表示上一次录音的原生层 stop
    // 尚未完成。主动停止残留录音机，提示用户重试。
    if (msg.indexOf("don't start") !== -1 || msg.indexOf('already') !== -1) {
      _setState('idle')
      uni.hideToast()
      uni.showToast({ title: '录音繁忙，请稍后重试', icon: 'none', duration: 2000 })
      try { _manager.stop() } catch (_) { /* ignore */ }
      return
    }

    _setState('idle')
    uni.hideToast()
    // 权限错误：引导用户去设置页打开
    if (msg.indexOf('auth') !== -1 || msg.indexOf('permission') !== -1 || msg.indexOf('deny') !== -1) {
      uni.showModal({
        title: '需要录音权限',
        content: '请在小程序设置中开启麦克风权限，用于语音输入。',
        confirmText: '去设置',
        success: function (modalRes) {
          if (modalRes.confirm) {
            // #ifdef MP-WEIXIN
            wx.openSetting({})
            // #endif
          }
        },
      })
    } else {
      uni.showToast({ title: msg + '，请使用文字输入', icon: 'none', duration: 2000 })
    }
  })

  return _manager
}

/**
 * 检查并请求录音权限，返回 true=已授权。
 */
function _checkPermission() {
  // #ifdef MP-WEIXIN
  return new Promise(function (resolve) {
    wx.getSetting({
      success: function (res) {
        if (res.authSetting['scope.record'] === false) {
          // 用户之前拒绝过 → 弹窗引导去设置
          uni.showModal({
            title: '需要录音权限',
            content: '请在设置中开启麦克风权限后重试',
            confirmText: '去设置',
            success: function (modalRes) {
              if (modalRes.confirm) {
                wx.openSetting({})
              }
              resolve(false)
            },
            fail: function () { resolve(false) },
          })
        } else if (res.authSetting['scope.record'] === true) {
          resolve(true)
        } else {
          // 未请求过 → 首次申请
          wx.authorize({
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
  // stopping 态：上次 onStop 未回调，拒绝并提示稍后重试
  if (_state === 'stopping') {
    uni.showToast({ title: '录音正在停止，请稍后', icon: 'none', duration: 1500 })
    return
  }
  // starting / recording 态：已经在录音或正在启动，拒绝重复 start
  if (_state !== 'idle') return

  _setState('starting')

  var ok = await _checkPermission()
  if (!ok) { _setState('idle'); return }

  // 快速点击（touchend 早于权限返回）时，handleVoiceEnd 可能已把状态置回 idle，
  // 此时不应继续启动录音（启动后没有对应的 stop → 录音卡死）。
  if (_state !== 'starting') { _setState('idle'); return }

  var manager = _getManager()
  if (!manager) { _setState('idle'); return }

  uni.showToast({ title: '正在聆听…', icon: 'none', duration: 60000 })

  // ⚠️ 不再无条件 manager.stop() 清理残留：
  // 状态机已防止重复 start（stopping 态拒绝，idle 态无残留录音）。
  // 原 L136 的清理 stop() 在 iOS 上会触发 "recorder not start" 错误，
  // 且其 onError 回调是异步的，不会被 catch 捕获。
  try {
    manager.start({
      format: 'wav',
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      duration: 60000,
    })
  } catch (e) {
    uni.hideToast()
    _setState('idle')
    throw e
  }
}

/**
 * 松手停止录音并上传识别 → Promise<string|null>。
 */
export function stopAndRecognize() {
  return new Promise(function (resolve) {
    // starting 态：onStart 还没回调，原生层尚未真正开始录音。
    // iOS 上此时调用 manager.stop() 会报 "recorder not start"。
    // 取消本次录音，直接返回 null。
    if (_state === 'starting') {
      _setState('idle')
      uni.hideToast()
      resolve(null)
      return
    }
    // idle / stopping 态：没有正在录音，或上次 stop 尚未回调，直接返回
    if (_state !== 'recording') {
      uni.hideToast()
      resolve(null)
      return
    }

    _setState('stopping')
    var manager = _getManager()
    if (!manager) { _setState('idle'); uni.hideToast(); resolve(null); return }

    manager.onStop(function (res) {
      _setState('idle')
      uni.hideToast()
      var tempFilePath = res && res.tempFilePath
      if (!tempFilePath) {
        uni.showToast({ title: '未录到语音，请重试', icon: 'none', duration: 1500 })
        resolve(null)
        return
      }
      _uploadAndRecognize(tempFilePath).then(resolve).catch(function () { resolve(null) })
    })

    manager.stop()
  })
}

/** 上传 WAV → 后端 ASR → 文本（base64 编码，走 request 域名白名单） */
function _uploadAndRecognize(filePath) {
  return new Promise(function (resolve, reject) {
    uni.showToast({ title: '识别中…', icon: 'loading', duration: 15000 })

    // 读文件 → base64 → JSON POST（绕过 uploadFile 域名白名单限制）
    // #ifdef MP-WEIXIN
    var fs = wx.getFileSystemManager()
    try {
      var base64 = fs.readFileSync(filePath, 'base64')
    } catch (e) {
      uni.hideToast()
      uni.showToast({ title: '读取录音文件失败，请使用文字输入', icon: 'none', duration: 2000 })
      reject(new Error('read failed'))
      return
    }

    var token = getToken()
    uni.request({
      url: BASE_URL + '/api/miniapp/voice/recognize/',
      method: 'POST',
      header: {
        'content-type': 'application/json',
        'Authorization': token ? 'Token ' + token : '',
      },
      data: JSON.stringify({ audio_base64: base64, format: 'wav' }),
      success: function (res) {
        uni.hideToast()
        var text = (res.data && res.data.text || '').trim()
        if (text) { resolve(text) }
        else {
          uni.showToast({ title: '未识别到内容，请重试', icon: 'none', duration: 2000 })
          reject(new Error('empty'))
        }
      },
      fail: function () {
        uni.hideToast()
        uni.showToast({ title: '语音识别暂不可用，请使用文字输入', icon: 'none', duration: 2000 })
        reject(new Error('request failed'))
      },
    })
    // #endif

    // #ifndef MP-WEIXIN
    uni.hideToast()
    uni.showToast({ title: '语音识别暂不可用，请使用文字输入', icon: 'none', duration: 2000 })
    reject(new Error('not wechat'))
    // #endif
  })
}
