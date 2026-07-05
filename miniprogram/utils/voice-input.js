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
var _recording = false

/** 获取或创建 RecorderManager（单例）。 */
function _getManager() {
  if (_manager) return _manager
  _manager = uni.getRecorderManager()

  _manager.onError(function (res) {
    console.warn('[voice-input] 录音错误:', JSON.stringify(res))
    _recording = false
    uni.hideToast()
    var msg = (res && (res.errMsg || res.message)) || '录音失败'
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
  if (_recording) return
  var ok = await _checkPermission()
  if (!ok) return

  var manager = _getManager()
  if (!manager) return

  _recording = true
  uni.showToast({ title: '正在聆听…', icon: 'none', duration: 60000 })

  manager.start({
    format: 'wav',
    sampleRate: 16000,
    numberOfChannels: 1,
    encodeBitRate: 48000,
    duration: 60000,
  })
}

/**
 * 松手停止录音并上传识别 → Promise<string|null>。
 */
export function stopAndRecognize() {
  return new Promise(function (resolve) {
    if (!_recording) { resolve(null); return }
    _recording = false

    var manager = _getManager()
    if (!manager) { uni.hideToast(); resolve(null); return }

    manager.onStop(function (res) {
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
