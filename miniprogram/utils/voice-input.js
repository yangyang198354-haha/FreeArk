/**
 * @module MOD-VOICE-INPUT
 * @description 语音输入封装（v1.12.0 MOD-P1208）
 *
 * 方案 B：微信原生 RecorderManager 录音 + 后端 ASR 转文字。
 * 因个人开发者无法授权同声传译插件（wx069ba97219f66d99），改用此方案。
 *
 * 流程：
 *   1. 长按录音按钮 → 开始录音（RecorderManager.start）
 *   2. 松手 → 停止录音，上传音频到后端 /api/miniapp/voice/recognize/
 *   3. 后端调用 ASR（百度/讯飞/腾讯云）→ 返回识别文本
 *   4. 任何异常均降级回退文本输入（fail-open）
 *
 * 后端 ASR 端点（待实现）：
 *   POST /api/miniapp/voice/recognize/  multipart {audio_file}
 *   → 200 {text: "识别结果"}
 *   → 4xx/5xx {detail: "错误信息"}
 *
 * 用法：
 *   import { startVoiceInput } from '@/utils/voice-input'
 *   const text = await startVoiceInput()
 *   if (text) { /* 发送识别结果 *!/ }
 */

import { api } from './api'

var _manager = null
var _recording = false

/** 获取或创建 RecorderManager 实例（懒初始化）。 */
function _getManager() {
  if (_manager) return _manager
  _manager = uni.getRecorderManager()

  _manager.onError(function (res) {
    console.warn('[voice-input] 录音错误:', res)
    _recording = false
    uni.hideToast()
    var msg = (res && (res.errMsg || res.message)) || '录音失败'
    uni.showToast({ title: msg + '，请使用文字输入', icon: 'none', duration: 2000 })
  })

  return _manager
}

/**
 * 长按开始录音。
 * 调用后显示"正在聆听…" toast，用户松手后调用 stopVoiceInput() 停止并识别。
 */
export function startRecording() {
  if (_recording) return
  var manager = _getManager()
  if (!manager) {
    uni.showToast({ title: '录音功能暂不可用，请使用文字输入', icon: 'none', duration: 2000 })
    return
  }
  _recording = true
  uni.showToast({ title: '正在聆听…', icon: 'none', duration: 60000 })
  manager.start({
    format: 'wav',
    sampleRate: 16000,
    numberOfChannels: 1,
    encodeBitRate: 48000,
  })
}

/**
 * 松手停止录音并上传识别，返回 Promise<string|null>。
 * 识别成功 → 返回文本；失败 → 返回 null（UI 层退回到文本输入）。
 */
export function stopAndRecognize() {
  return new Promise(function (resolve) {
    if (!_recording) {
      resolve(null)
      return
    }
    _recording = false

    var manager = _getManager()
    if (!manager) {
      uni.hideToast()
      resolve(null)
      return
    }

    // 监听录音停止 → 拿到临时文件 → 上传识别
    manager.onStop(function (res) {
      uni.hideToast()
      var tempFilePath = res && res.tempFilePath
      if (!tempFilePath) {
        uni.showToast({ title: '未录到语音，请重试', icon: 'none', duration: 1500 })
        resolve(null)
        return
      }

      // 上传到后端 ASR 端点
      _uploadAndRecognize(tempFilePath)
        .then(function (text) { resolve(text) })
        .catch(function () { resolve(null) })
    })

    manager.stop()
  })
}

/**
 * 上传音频文件到后端 ASR 端点，返回识别文本。
 * 端点未就绪时降级提示。
 */
function _uploadAndRecognize(filePath) {
  return new Promise(function (resolve, reject) {
    // 尝试调用后端 ASR 端点（v1.12.0 先占位，端点未实现时优雅降级）
    uni.showToast({ title: '识别中…', icon: 'loading', duration: 15000 })

    uni.uploadFile({
      url: api._baseUrl + '/miniapp/voice/recognize/',
      filePath: filePath,
      name: 'audio_file',
      header: api._getAuthHeader ? api._getAuthHeader() : {},
      success: function (res) {
        uni.hideToast()
        try {
          var data = JSON.parse(res.data)
          var text = (data && data.text || '').trim()
          if (text) {
            resolve(text)
          } else {
            uni.showToast({ title: '未识别到语音内容，请重试', icon: 'none', duration: 2000 })
            reject(new Error('empty text'))
          }
        } catch (_) {
          uni.showToast({ title: '语音识别暂不可用，请使用文字输入', icon: 'none', duration: 2000 })
          reject(new Error('parse error'))
        }
      },
      fail: function () {
        uni.hideToast()
        uni.showToast({ title: '语音识别暂不可用，请使用文字输入', icon: 'none', duration: 2000 })
        reject(new Error('upload failed'))
      },
    })
  })
}
