/**
 * @vitest-environment node
 * voice-input 状态机测试 — 覆盖 iOS 上 start()/stop() 回调延迟导致的边界情况。
 *
 * 核心验证点：
 *   - idle → starting → recording → stopping → idle 正常流转
 *   - starting 态松手（onStart 未回调）→ 返回 null，不调用 manager.stop()
 *   - stopping 态再次 startRecording → 被拒绝，不调用 manager.start()
 *   - onError 对 iOS 特有错误的静默处理
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// 伪 RecorderManager：捕获 onStart/onStop/onError 回调，便于模拟原生层时序
function makeFakeRecorder() {
  const handlers = {}
  return {
    onStart: (cb) => { handlers.start = cb },
    onStop: (cb) => { handlers.stop = cb },
    onError: (cb) => { handlers.error = cb },
    start: vi.fn(),
    stop: vi.fn(),
    // 测试辅助：模拟原生层回调
    emitStart: () => handlers.start && handlers.start(),
    emitStop: (res) => handlers.stop && handlers.stop(res || {}),
    emitError: (res) => handlers.error && handlers.error(res),
  }
}

let recorder

beforeEach(() => {
  vi.resetModules()
  recorder = makeFakeRecorder()
  globalThis.uni.getRecorderManager = vi.fn(() => recorder)
  // wx.authorize 默认成功，便于走通权限检查
  globalThis.wx.getSetting = vi.fn(({ success }) => success({ authSetting: { 'scope.record': true } }))
  globalThis.wx.getFileSystemManager = vi.fn(() => ({ readFileSync: () => 'base64data' }))
  globalThis.uni.request = vi.fn(({ success }) => success({ data: { text: '识别结果' } }))
})

describe('voice-input 状态机 — 正常流程', () => {
  it('idle → starting → recording → stopping → idle 全流程', async () => {
    const { startRecording, stopAndRecognize } = await import('@/utils/voice-input')

    await startRecording()
    expect(recorder.start).toHaveBeenCalledTimes(1)
    // 此时状态应是 starting（onStart 未触发）

    recorder.emitStart()
    // 现在状态应是 recording，stopAndRecognize 应正常调用 manager.stop()

    const promise = stopAndRecognize()
    expect(recorder.stop).toHaveBeenCalledTimes(1)

    recorder.emitStop({ tempFilePath: '/tmp/voice.wav' })
    const result = await promise
    expect(result).toBe('识别结果')
  })
})

describe('voice-input 状态机 — iOS 边界情况', () => {
  it('starting 态松手（onStart 未回调）→ 返回 null，不调用 stop()', async () => {
    const { startRecording, stopAndRecognize } = await import('@/utils/voice-input')

    await startRecording()
    // 不触发 emitStart，直接松手
    const result = await stopAndRecognize()

    expect(result).toBeNull()
    expect(recorder.stop).not.toHaveBeenCalled()
  })

  it('stopping 态再次 startRecording → 被拒绝，不调用 start()', async () => {
    const { startRecording, stopAndRecognize } = await import('@/utils/voice-input')

    await startRecording()
    recorder.emitStart()  // 进入 recording
    stopAndRecognize()     // 进入 stopping（onStop 未回调）

    await startRecording() // 再次 start，应被拒绝
    expect(recorder.start).toHaveBeenCalledTimes(1) // 仍只有第一次的调用
    expect(uni.showToast).toHaveBeenCalledWith(
      expect.objectContaining({ title: '录音正在停止，请稍后' })
    )
  })

  it('starting 态再次 startRecording → 被拒绝', async () => {
    const { startRecording } = await import('@/utils/voice-input')

    await startRecording()
    // 不触发 emitStart，仍在 starting 态
    await startRecording()
    expect(recorder.start).toHaveBeenCalledTimes(1)
  })

  it('idle 态直接 stopAndRecognize → 返回 null，不调用 stop()', async () => {
    const { stopAndRecognize } = await import('@/utils/voice-input')

    const result = await stopAndRecognize()
    expect(result).toBeNull()
    expect(recorder.stop).not.toHaveBeenCalled()
  })
})

describe('voice-input onError — iOS 特有错误静默处理', () => {
  it('"recorder not start" 静默处理，不弹错误 toast', async () => {
    const { startRecording } = await import('@/utils/voice-input')
    await startRecording()

    recorder.emitError({ errMsg: 'operateRecorder:fail recorder not start' })

    // 不应调用 showToast 显示错误信息（hideToast 是预期的，showToast 带错误信息不是）
    const showToastCalls = uni.showToast.mock.calls
    const errorToasts = showToastCalls.filter(c =>
      c[0] && c[0].title && c[0].title.indexOf('recorder not start') !== -1
    )
    expect(errorToasts).toHaveLength(0)
  })

  it('"is recording or paused" 静默处理', async () => {
    const { startRecording } = await import('@/utils/voice-input')
    await startRecording()

    recorder.emitError({ errMsg: 'operateRecorder:fail is recording or paused' })

    const errorToasts = uni.showToast.mock.calls.filter(c =>
      c[0] && c[0].title && c[0].title.indexOf('is recording') !== -1
    )
    expect(errorToasts).toHaveLength(0)
  })
})
