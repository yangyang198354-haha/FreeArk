/**
 * Unit tests for MOD-003: MediaUploader (miniprogram/utils/media-uploader.js)
 * TC-UNIT-007 ~ TC-UNIT-027
 *
 * Covers:
 *   - isUploadIdExpired: pure function with all boundary cases
 *   - uploadImage: mock uni.uploadFile success/fail/timeout paths
 *   - uploadImages: Promise.allSettled aggregation
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// We must mock the http and auth imports BEFORE importing the module
vi.mock('@/utils/http', () => ({
  BASE_URL: 'https://api.freeark.example.com',
  WS_BASE_URL: 'wss://api.freeark.example.com',
}))

vi.mock('@/utils/auth', () => ({
  getToken: vi.fn(() => 'test-token-abc123'),
}))

import { uploadImage, uploadImages, isUploadIdExpired, DEFAULT_TTL_MS } from '@/utils/media-uploader'
import { getToken } from '@/utils/auth'

describe('utils/media-uploader — isUploadIdExpired 纯函数', () => {
  /** Freeze Date.now to a fixed value for deterministic testing */
  const NOW = 1000000

  beforeEach(() => {
    vi.spyOn(Date, 'now').mockReturnValue(NOW)
  })

  // TC-UNIT-007: Just uploaded (0 seconds ago)
  it('TC-UNIT-007: 刚上传(0s前) → 未过期', () => {
    expect(isUploadIdExpired(NOW)).toBe(false)
  })

  // TC-UNIT-008: 499 seconds ago
  it('TC-UNIT-008: 499s前 → 未过期 (diff=499000 < 500000)', () => {
    expect(isUploadIdExpired(NOW - 499000)).toBe(false)
  })

  // TC-UNIT-009: 500 seconds ago (boundary)
  it('TC-UNIT-009: 500s前(边界) → 未过期 (diff=500000 <= 500000)', () => {
    expect(isUploadIdExpired(NOW - 500000)).toBe(false)
  })

  // TC-UNIT-010: 501 seconds ago
  it('TC-UNIT-010: 501s前 → 过期 (diff=501000 > 500000)', () => {
    expect(isUploadIdExpired(NOW - 501000)).toBe(true)
  })

  // TC-UNIT-011: 3600 seconds ago (way past TTL)
  it('TC-UNIT-011: 3600s前 → 过期', () => {
    expect(isUploadIdExpired(NOW - 3600000)).toBe(true)
  })

  // TC-UNIT-012: negative uploadedAt
  it('TC-UNIT-012: 负数uploadedAt → 过期 (防御性)', () => {
    expect(isUploadIdExpired(-5000)).toBe(true)
  })

  // TC-UNIT-013: uploadedAt = 0
  it('TC-UNIT-013: uploadedAt=0 → 过期 (falsy check)', () => {
    expect(isUploadIdExpired(0)).toBe(true)
  })

  // TC-UNIT-014: null/undefined uploadedAt
  it('TC-UNIT-014: null → 过期 (falsy)', () => {
    expect(isUploadIdExpired(null)).toBe(true)
  })

  it('TC-UNIT-014-b: undefined → 过期 (falsy)', () => {
    expect(isUploadIdExpired(undefined)).toBe(true)
  })

  // TC-UNIT-015: custom maxAgeMs
  it('TC-UNIT-015: 自定义maxAgeMs=1000 → diff=500<=1000 未过期', () => {
    expect(isUploadIdExpired(NOW - 500, 1000)).toBe(false)
  })

  it('TC-UNIT-015-b: 自定义maxAgeMs=1000 → diff=1500>1000 过期', () => {
    expect(isUploadIdExpired(NOW - 1500, 1000)).toBe(true)
  })

  // Verify DEFAULT_TTL_MS constant
  it('DEFAULT_TTL_MS = 500000 (500s, 留100s buffer)', () => {
    expect(DEFAULT_TTL_MS).toBe(500000)
  })
})

describe('utils/media-uploader — uploadImage (mock uni.uploadFile)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // TC-UNIT-021: Successful upload
  it('TC-UNIT-021: 成功上传 → resolve {upload_id, expires_in, uploaded_at}', async () => {
    uni.uploadFile.mockImplementation(({ success }) => {
      success({
        statusCode: 200,
        data: JSON.stringify({ upload_id: 'uuid-test-001', expires_in: 600 }),
      })
    })

    const result = await uploadImage('/tmp/photo.jpg')

    expect(result).toMatchObject({
      upload_id: 'uuid-test-001',
      expires_in: 600,
    })
    expect(typeof result.uploaded_at).toBe('number')

    // Verify upload was called correctly
    expect(uni.uploadFile).toHaveBeenCalledWith(
      expect.objectContaining({
        url: 'https://api.freeark.example.com/api/chat/image-upload/',
        filePath: '/tmp/photo.jpg',
        name: 'image',
      })
    )

    // Verify auth header was sent
    const callArgs = uni.uploadFile.mock.calls[0][0]
    expect(callArgs.header.Authorization).toBe('Token test-token-abc123')
  })

  // TC-UNIT-022: HTTP error response
  it('TC-UNIT-022: HTTP错误(400) → reject {code, message, filePath}', async () => {
    uni.uploadFile.mockImplementation(({ success }) => {
      success({
        statusCode: 400,
        data: JSON.stringify({ error: '文件过大' }),
      })
    })

    await expect(uploadImage('/tmp/large.jpg')).rejects.toMatchObject({
      code: 'UPLOAD_FAILED',
      message: '文件过大',
      filePath: '/tmp/large.jpg',
    })
  })

  // TC-UNIT-023: Network error
  it('TC-UNIT-023: 网络错误 → reject {code:\'NETWORK_ERROR\'}', async () => {
    uni.uploadFile.mockImplementation(({ fail }) => {
      fail({ errMsg: 'uploadFile:fail timeout' })
    })

    await expect(uploadImage('/tmp/photo.jpg')).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      message: 'uploadFile:fail timeout',
      filePath: '/tmp/photo.jpg',
    })
  })

  // TC-UNIT-024: JSON parse error in response
  it('TC-UNIT-024: 响应JSON解析失败 → reject {code:\'UPLOAD_FAILED\'}', async () => {
    uni.uploadFile.mockImplementation(({ success }) => {
      success({
        statusCode: 200,
        data: '<html>Not JSON</html>',
      })
    })

    await expect(uploadImage('/tmp/photo.jpg')).rejects.toMatchObject({
      code: 'UPLOAD_FAILED',
      message: '服务器响应异常',
    })
  })

  // Bonus: no token → header without Authorization
  it('无token时不发送Authorization header', async () => {
    getToken.mockReturnValueOnce(null)

    uni.uploadFile.mockImplementation(({ success }) => {
      success({
        statusCode: 200,
        data: JSON.stringify({ upload_id: 'uuid-noauth', expires_in: 600 }),
      })
    })

    const result = await uploadImage('/tmp/photo.jpg')
    expect(result.upload_id).toBe('uuid-noauth')

    const callArgs = uni.uploadFile.mock.calls[0][0]
    expect(callArgs.header.Authorization).toBeUndefined()
  })

  // Bonus: response with .detail fallback
  it('错误响应使用detail字段fallback', async () => {
    uni.uploadFile.mockImplementation(({ success }) => {
      success({
        statusCode: 500,
        data: JSON.stringify({ detail: '服务器内部错误' }),
      })
    })

    await expect(uploadImage('/tmp/photo.jpg')).rejects.toMatchObject({
      code: 'UPLOAD_FAILED',
      message: '服务器内部错误',
    })
  })

  // Bonus: success response with default expires_in
  it('成功响应无expires_in → 默认600', async () => {
    uni.uploadFile.mockImplementation(({ success }) => {
      success({
        statusCode: 200,
        data: JSON.stringify({ upload_id: 'uuid-nottl' }),
      })
    })

    const result = await uploadImage('/tmp/photo.jpg')
    expect(result.expires_in).toBe(600)
  })
})

describe('utils/media-uploader — uploadImages (Promise.allSettled)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // TC-UNIT-025: All succeed
  it('TC-UNIT-025: 全部上传成功 → 全部fulfilled', async () => {
    uni.uploadFile.mockImplementation(({ success }) => {
      success({
        statusCode: 200,
        data: JSON.stringify({ upload_id: 'uuid-batch', expires_in: 600 }),
      })
    })

    const results = await uploadImages(['a.jpg', 'b.jpg', 'c.jpg'])

    expect(results).toHaveLength(3)
    results.forEach((r) => {
      expect(r.status).toBe('fulfilled')
      expect(r.value.upload_id).toBe('uuid-batch')
    })
  })

  // TC-UNIT-026: Mixed success/failure
  it('TC-UNIT-026: 混合成功失败 → fulfilled + rejected 共存', async () => {
    let callCount = 0
    uni.uploadFile.mockImplementation((opts) => {
      callCount++
      if (callCount === 1) {
        opts.success({
          statusCode: 200,
          data: JSON.stringify({ upload_id: 'uuid-ok', expires_in: 600 }),
        })
      } else {
        opts.fail({ errMsg: 'uploadFile:fail' })
      }
    })

    const results = await uploadImages(['a.jpg', 'b.jpg'])

    expect(results).toHaveLength(2)
    expect(results[0].status).toBe('fulfilled')
    expect(results[1].status).toBe('rejected')
  })

  // TC-UNIT-027: Empty filePaths
  it('TC-UNIT-027: 空数组 → 返回[]', async () => {
    const results = await uploadImages([])
    expect(results).toEqual([])
    expect(uni.uploadFile).not.toHaveBeenCalled()
  })

  // Bonus: null/undefined filePaths
  it('filePaths为null → 返回[]', async () => {
    const results = await uploadImages(null)
    expect(results).toEqual([])
  })
})
