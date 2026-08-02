/**
 * @module MOD-VOICE-INPUT
 * @description 语音输入封装（v1.8.1）
 *
 * 微信原生 RecorderManager 录音 → WAV 上传 → 后端 Sherpa-ONNX ASR。
 * fail-open：任何异常降级回退文本输入。
 *
 * 多端应用 APK 兼容：
 *   微信多端小程序打包 APK 后，运行时基于 MP-WEIXIN 代码，但已脱离微信权限体系。
 *   v1.8.0: wx.getAppAuthorizeSetting 在部分 APK 运行时中回调永不触发，
 *   因此 APK 路径改为直接尝试录音，由 onError 回调处理权限拒绝，
 *   manifest.json 中已声明 RECORD_AUDIO，Android 安装时已授予。
 *
 * v1.8.1 — onStart 超时降级（关键修复）：
 *   manager.start() 调用成功后录音实际已在运行，onStart 回调可能延迟。
 *   旧代码把 onStart 超时当失败处理，销毁录音并报错 → 录音文件丢失。
 *   修复：onStart 超时后降级为 recording 状态，录音继续，松手可正常停止和上传。
 *
 * v1.8.0 — 权限检查策略重构：
 *   - APK 路径：getAppAuthorizeSetting 添加 1.5s 超时 → 超时默认放行
 *     （Android 权限已由 manifest 声明 + onError 处理拒绝）
 *   - 微信小程序路径：保持 getSetting/authorize 流程不变
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
// 状态机：'idle' | 'starting' | 'recording' | 'stopping'
var _state = 'idle'
// generation 计数器：每次 startRecording 递增，用于防止过期的异步回调覆盖新状态
var _generation = 0
// onStop 回调队列：FIFO，入队 push，出队 shift
var _onStopQueue = []
// onStart 回调队列：FIFO，入队 push，出队 shift
var _onStartQueue = []
// 是否已注册 onStop / onStart（只注册一次）
var _onStopRegistered = false
var _onStartRegistered = false
// 取消令牌：stopAndRecognize 可取消仍在进行的 startRecording
var _cancelStart = null
// onError 中权限弹窗是否已显示（防重复弹窗）
var _authModalShown = false
// 状态变化回调：通知调用方录音状态变化（用于 UI 同步）
var _onStateChange = null

function _isStarting() { return _state === 'starting' }
function _isRecording() { return _state === 'recording' }
function _isActive() { return _state === 'starting' || _state === 'recording' }

/** 设置状态变化回调，用于 UI 同步 */
export function setStateChangeCallback(cb) {
  _onStateChange = cb
}

/** 通知状态变化 */
function _notifyStateChange(newState) {
  if (_onStateChange) {
    try { _onStateChange(newState) } catch (_) { /* ignore */ }
  }
}

/**
 * 运行时判断是否在多端应用 APK 中运行。
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

    // "stop record fail" 是清理残留录音的预期行为
    if (msg.indexOf('stop record fail') !== -1) {
      uni.hideToast()
      return
    }

    // "audio is recording, don't start again" → 主动停止残留
    if (msg.indexOf("don't start") !== -1 || msg.indexOf('already') !== -1) {
      _state = 'idle'
      _notifyStateChange('idle')
      uni.hideToast()
      uni.showToast({ title: '录音繁忙，请稍后重试', icon: 'none', duration: 2000 })
      try { _manager.stop() } catch (_) { /* ignore */ }
      return
    }

    _state = 'idle'
    _notifyStateChange('idle')
    uni.hideToast()
    if (msg.indexOf('auth') !== -1 || msg.indexOf('permission') !== -1 || msg.indexOf('deny') !== -1) {
      // 权限相关错误：弹窗引导用户授权
      if (!_authModalShown) {
        _authModalShown = true
        uni.showModal({
          title: '需要录音权限',
          content: '请在系统设置中开启麦克风权限，用于语音输入。',
          confirmText: '去设置',
          success: function (modalRes) {
            _authModalShown = false
            if (modalRes.confirm) {
              if (_isMultiTerminalApp()) {
                try { wx.openAppAuthorizeSetting({}) } catch (_) { /* ignore */ }
              } else {
                try { uni.openSetting({}) } catch (_) { /* ignore */ }
              }
            }
          },
          fail: function () { _authModalShown = false },
        })
      }
    } else {
      uni.showToast({ title: msg + '，请使用文字输入', icon: 'none', duration: 2000 })
    }
  })

  // onStop：录音停止后触发（由 stop() 或自动 duration 结束）
  _manager.onStop(function (res) {
    _log('onStop', '触发', res ? { tempFilePath: res.tempFilePath, fileSize: res.fileSize, duration: res.duration } : null)
    _state = 'idle'
    _notifyStateChange('idle')
    uni.hideToast()
    var cb = _onStopQueue.shift()
    if (cb) cb(res)
  })
  _onStopRegistered = true

  // onStart：录音真正开始时触发
  _manager.onStart(function () {
    _log('onStart', '触发，录音已真正启动')
    var cb = _onStartQueue.shift()
    if (cb) cb()
  })
  _onStartRegistered = true

  return _manager
}

/**
 * 检查并请求录音权限，返回 true=已授权。
 *
 * v1.8.0 — APK 路径策略变更：
 *   wx.getAppAuthorizeSetting 在部分多端 APK 运行时中回调永不触发（success/fail 均不调用），
 *   导致 startRecording 永久卡死。修复方案：
 *   1. 给 getAppAuthorizeSetting 添加 1.5s 超时安全网
 *   2. 超时默认放行 true（Android 权限由 manifest + onError 兜底处理）
 *   3. 只有明确返回 denied 才拦截
 */
function _checkPermission() {
  if (_isMultiTerminalApp()) {
    _log('权限检查', '多端 APK：调用 wx.getAppAuthorizeSetting（带 1.5s 超时）')
    return new Promise(function (resolve) {
      var settled = false
      function finish(val) {
        if (settled) return
        settled = true
        resolve(val)
      }

      // 1.5 秒超时安全网：超时默认放行
      var timer = setTimeout(function () {
        _log('权限检查', 'getAppAuthorizeSetting 超时（1.5s），默认放行')
        finish(true)
      }, 1500)

      try {
        wx.getAppAuthorizeSetting({
          success: function (res) {
            clearTimeout(timer)
            _log('权限检查', 'getAppAuthorizeSetting 成功', res)
            var state = res && res.microphoneAuthorized
            if (state === 'denied') {
              // 明确拒绝：弹窗引导用户去设置
              uni.showModal({
                title: '需要录音权限',
                content: '请在系统设置中开启麦克风权限后重试',
                confirmText: '去设置',
                success: function (modalRes) {
                  if (modalRes.confirm) {
                    try { wx.openAppAuthorizeSetting({}) } catch (_) { /* ignore */ }
                  }
                  finish(false)
                },
                fail: function () { finish(false) },
              })
            } else {
              // authorized 或 not determined：放行
              finish(true)
            }
          },
          fail: function (err) {
            clearTimeout(timer)
            _log('权限检查', 'getAppAuthorizeSetting 失败，默认放行', err)
            finish(true)  // 失败也放行，由 onError 兜底
          },
        })
      } catch (e) {
        clearTimeout(timer)
        _log('权限检查', 'getAppAuthorizeSetting 异常，默认放行', e && e.message)
        finish(true)
      }
    })
  }

  // 微信小程序路径：保持原有 getSetting/authorize 流程
  _log('权限检查', '微信小程序：调用 uni.getSetting')
  return new Promise(function (resolve) {
    uni.getSetting({
      success: function (res) {
        if (res.authSetting['scope.record'] === false) {
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
}

/**
 * 长按开始录音。
 *
 * 状态机：idle → starting → recording
 *  - 进入 'starting'：防双击、允许 stopAndRecognize 取消
 *  - onStart 回调后进入 'recording'：确认录音真正开始
 *  - 失败时回到 'idle'
 *
 * v1.8.0：APK 路径超时安全网确保权限检查不会永久阻塞。
 */
export async function startRecording() {
  if (_isActive()) { _log('start', '忽略：已处于 ' + _state + ' 状态'); return }

  var myGen = ++_generation
  _state = 'starting'
  _notifyStateChange('starting')
  var cancelled = false
  _cancelStart = function () { cancelled = true }

  _log('start', '进入 starting 状态 gen=' + myGen)

  var ok = await _checkPermission()

  // 检查是否已被更新的调用取代（generation 已过期）
  if (myGen !== _generation) {
    _log('start', 'generation 已过期（新录音已启动），放弃')
    return
  }

  if (!ok) {
    if (_state === 'starting') { _state = 'idle'; _notifyStateChange('idle') }
    _cancelStart = null
    _log('start', '权限检查失败')
    if (!cancelled) throw new Error('录音权限未授权')
    return
  }

  if (cancelled) {
    if (_state === 'starting') { _state = 'idle'; _notifyStateChange('idle') }
    _cancelStart = null
    _log('start', '已被取消（松手早于启动完成）')
    return
  }

  var manager = _getManager()
  if (!manager) {
    if (_state === 'starting') { _state = 'idle'; _notifyStateChange('idle') }
    _cancelStart = null
    throw new Error('录音管理器不可用')
  }

  uni.showToast({ title: '正在聆听…', icon: 'none', duration: 60000 })

  // 清理可能的残留录音
  try { manager.stop() } catch (_) { /* ignore */ }

  // 等待 onStart 回调确认（3 秒超时）
  // v1.8.1 修复：onStart 超时不等于录音失败。manager.start() 调用成功后，录音实际已在运行，
  // onStart 回调可能延迟数百毫秒到数秒。超时后降级为 recording 状态，不销毁录音。
  var startSettled = false
  var startPromise = new Promise(function (resolve) {
    _onStartQueue.push(function () {
      if (startSettled) return
      startSettled = true
      resolve()
    })
    setTimeout(function () {
      if (startSettled) return
      startSettled = true
      _log('start', 'onStart 超时（3s），降级为 recording 状态（录音实际已在运行）')
      resolve()  // 超时也 resolve，不 reject
    }, 3000)
  })

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
    if (_state === 'starting') { _state = 'idle'; _notifyStateChange('idle') }
    _cancelStart = null
    uni.hideToast()
    _onStartQueue.shift()
    _log('start', 'manager.start() 异常', e && e.message)
    throw e
  }

  await startPromise

  // 检查 generation：是否被新的调用取代
  if (myGen !== _generation) {
    _log('start', 'onStart 已触发但 generation 已过期')
    try { manager.stop() } catch (_) { /* ignore */ }
    return
  }

  if (cancelled) {
    if (_state === 'starting') { _state = 'idle'; _notifyStateChange('idle') }
    _cancelStart = null
    _log('start', 'onStart 已触发但已被取消')
    try { manager.stop() } catch (_) { /* ignore */ }
    return
  }

  _state = 'recording'
  _notifyStateChange('recording')
  _cancelStart = null
  _log('start', 'recording 状态，录音已启动')
}

/**
 * 松手停止录音并上传识别 → Promise<string|null>。
 *
 * 状态机处理：
 *  - 'starting'：录音还未真正启动，取消启动流程，立即重置 _state，返回 null
 *  - 'recording'：正常 stop → onStop → 上传识别
 *
 * 超时兜底：onStop 5 秒未触发 → 尝试 getTempFiles() → 失败则提示。
 */
export function stopAndRecognize() {
  _log('stopAndRecognize', '进入，state=' + _state)

  // 取消正在进行的启动流程
  if (_isStarting()) {
    _log('stopAndRecognize', '取消 starting 状态的启动流程')
    if (_cancelStart) _cancelStart()
    // 立即重置状态，允许快速重试
    _state = 'idle'
    _notifyStateChange('idle')
    // 递增 generation，使旧 startRecording 的异步回调自动失效
    _generation++
    return Promise.resolve(null)
  }

  if (!_isRecording()) {
    _log('stopAndRecognize', '非 recording 状态，返回 null')
    return Promise.resolve(null)
  }

  _state = 'stopping'
  _notifyStateChange('stopping')

  return new Promise(function (resolve) {
    var manager = _getManager()
    if (!manager) { uni.hideToast(); _state = 'idle'; _notifyStateChange('idle'); resolve(null); return }

    var resolved = false
    function done(val) { if (resolved) return; resolved = true; clearTimeout(timer); resolve(val) }

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

    // 5 秒超时兜底
    var timer = setTimeout(function () {
      _log('stopAndRecognize', '⚠️ onStop 5 秒未触发，尝试兜底读取')
      // FIFO：shift 出队最早的回调
      var cb = _onStopQueue.shift()
      if (cb) {
        cb(null)
      }
      // 兜底：尝试 getTempFiles
      try {
        if (manager.getTempFiles) {
          var files = manager.getTempFiles()
          _log('stopAndRecognize', '兜底：getTempFiles 返回', files)
          if (files && files.length > 0) {
            var path = files[0]
            uni.hideToast()
            _uploadAndRecognize(path).then(done).catch(function () { done(null) })
            return
          }
        }
      } catch (e) {
        _log('stopAndRecognize', '兜底读取失败', e && e.message)
      }
      uni.hideToast()
      uni.showModal({
        title: '录音异常',
        content: '录音未正常结束，请重试或使用文字输入',
        showCancel: false,
        confirmText: '知道了',
      })
      done(null)
    }, 5000)

    try {
      manager.stop()
      _log('stopAndRecognize', 'manager.stop() 调用成功')
    } catch (e) {
      _log('stopAndRecognize', 'manager.stop() 异常', e && e.message)
      clearTimeout(timer)
      var failCb = _onStopQueue.shift()
      if (failCb) failCb(null)
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
