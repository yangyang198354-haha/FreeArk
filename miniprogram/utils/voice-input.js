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
            uni.openSetting({})
            // #endif
            // #ifdef APP-PLUS
            // APP 端无 openSetting，提示用户去系统设置
            if (plus.os && plus.os.name === 'Android') {
              try {
                var Intent = plus.android.importClass('android.content.Intent')
                var Settings = plus.android.importClass('android.provider.Settings')
                var Uri = plus.android.importClass('android.net.Uri')
                var intent = new Intent()
                intent.setAction(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                intent.setData(Uri.fromParts('package', plus.runtime.appid, null))
                plus.android.runtimeMainActivity().startActivity(intent)
              } catch (e) { /* ignore */ }
            }
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
  // #ifdef APP-PLUS
  return new Promise(function (resolve) {
    if (plus.os && plus.os.name === 'Android') {
      try {
        var main = plus.android.runtimeMainActivity()
        var granted = plus.android.invoke(main, 'checkSelfPermission', 'android.permission.RECORD_AUDIO')
        if (granted === 0) {
          resolve(true)
        } else {
          plus.android.requestPermissions(
            ['android.permission.RECORD_AUDIO'],
            function (e) {
              var result = e.granted && e.granted.length > 0
              if (!result) {
                uni.showToast({ title: '录音权限未开启，请在系统设置中允许', icon: 'none', duration: 2000 })
              }
              resolve(result)
            },
            function () { resolve(false) }
          )
        }
      } catch (e) { resolve(false) }
    } else {
      resolve(true)
    }
  })
  // #endif
  // #ifndef MP-WEIXIN || APP-PLUS
  return Promise.resolve(true)
  // #endif
}

/**
 * 长按开始录音。
 */
export async function startRecording() {
  if (_recording) return

  // ⚠️  Set _recording BEFORE await to close the double-tap race window.
  //     If permission check fails we reset it below.
  _recording = true

  var ok = await _checkPermission()
  if (!ok) { _recording = false; return }

  var manager = _getManager()
  if (!manager) { _recording = false; return }

  uni.showToast({ title: '正在聆听…', icon: 'none', duration: 60000 })

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
  } catch (e) {
    uni.hideToast()
    _recording = false
    throw e
  }
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
    var fs = uni.getFileSystemManager()
    try {
      var base64 = fs.readFileSync(filePath, 'base64')
    } catch (e) {
      uni.hideToast()
      uni.showToast({ title: '读取录音文件失败，请使用文字输入', icon: 'none', duration: 2000 })
      reject(new Error('read failed'))
      return
    }
    _postAudioBase64(base64, resolve, reject)
    // #endif

    // #ifdef APP-PLUS
    // APP 端使用 plus.io 读取文件并转 base64
    plus.io.resolveLocalFileSystemURL(filePath, function (entry) {
      entry.file(function (file) {
        try {
          var reader = new plus.io.FileReader()
          reader.onloadend = function (e) {
            // e.target.result 形如 "data:audio/wav;base64,XXXX"，需剥离前缀
            var dataUrl = e.target.result || ''
            var commaIdx = dataUrl.indexOf(',')
            var base64 = commaIdx >= 0 ? dataUrl.substring(commaIdx + 1) : dataUrl
            if (!base64) {
              uni.hideToast()
              uni.showToast({ title: '读取录音文件失败，请使用文字输入', icon: 'none', duration: 2000 })
              reject(new Error('read empty'))
              return
            }
            _postAudioBase64(base64, resolve, reject)
          }
          reader.onerror = function () {
            uni.hideToast()
            uni.showToast({ title: '读取录音文件失败，请使用文字输入', icon: 'none', duration: 2000 })
            reject(new Error('read failed'))
          }
          reader.readAsDataURL(file)
        } catch (e) {
          uni.hideToast()
          uni.showToast({ title: '读取录音文件失败，请使用文字输入', icon: 'none', duration: 2000 })
          reject(new Error('read failed'))
        }
      }, function () {
        uni.hideToast()
        uni.showToast({ title: '读取录音文件失败，请使用文字输入', icon: 'none', duration: 2000 })
        reject(new Error('file entry failed'))
      })
    }, function () {
      uni.hideToast()
      uni.showToast({ title: '读取录音文件失败，请使用文字输入', icon: 'none', duration: 2000 })
      reject(new Error('resolve failed'))
    })
    // #endif

    // #ifndef MP-WEIXIN || APP-PLUS
    uni.hideToast()
    uni.showToast({ title: '语音识别暂不可用，请使用文字输入', icon: 'none', duration: 2000 })
    reject(new Error('not supported'))
    // #endif
  })
}

/** 将 base64 音频 POST 到后端 ASR 接口 */
function _postAudioBase64(base64, resolve, reject) {
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
}
