/**
 * @module MOD-003
 * @implements IFC-003-01, IFC-003-02, IFC-003-03
 * @author sub_agent_software_developer
 * @description Media uploader for WeChat Mini Program (ADR-002, ADR-007).
 *   Uploads images to POST /api/chat/image-upload/ via uni.uploadFile (multipart/form-data).
 *   Manages upload_id TTL lifecycle with client-side expiry detection.
 *
 *   Reference implementation: api.js uploadProfile() (uni.uploadFile pattern).
 *
 * Usage:
 *   import { uploadImage, uploadImages, isUploadIdExpired } from '@/utils/media-uploader'
 *   const result = await uploadImage('/tmp/photo.jpg')
 *   // result: { upload_id: 'uuid4', expires_in: 600, uploaded_at: 1712345678000 }
 */

import { BASE_URL } from './http'
import { getToken } from './auth'

/** Default max age: 500 seconds (server TTL is 600s, leave 100s buffer). */
export const DEFAULT_TTL_MS = 500000

/** Upload endpoint path. */
const UPLOAD_PATH = '/api/chat/image-upload/'

/**
 * Upload a single image file.
 *
 * @param {string} filePath - Temporary file path from uni.chooseImage
 * @param {object} [options] - Optional configuration
 * @param {AbortSignal} [options.signal] - Not supported in Mini Program; reserved for API parity
 * @returns {Promise<{upload_id: string, expires_in: number, uploaded_at: number}>}
 * @throws {object} UploadError with { code, message, filePath }
 */
export function uploadImage(filePath, options = {}) {
  const token = getToken()
  const authHeader = {}
  if (token) {
    authHeader['Authorization'] = 'Token ' + token
  }

  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: BASE_URL + UPLOAD_PATH,
      filePath: filePath,
      name: 'image',
      header: authHeader,
      success: (uploadRes) => {
        try {
          const data = JSON.parse(uploadRes.data)
          if (uploadRes.statusCode >= 200 && uploadRes.statusCode < 300) {
            resolve({
              upload_id: data.upload_id,
              expires_in: data.expires_in || 600,
              uploaded_at: Date.now()
            })
          } else {
            reject({
              code: 'UPLOAD_FAILED',
              message: data.error || data.detail || '图片上传失败',
              filePath: filePath
            })
          }
        } catch (e) {
          reject({
            code: 'UPLOAD_FAILED',
            message: '服务器响应异常',
            filePath: filePath
          })
        }
      },
      fail: (err) => {
        reject({
          code: 'NETWORK_ERROR',
          message: err.errMsg || '网络错误，上传失败',
          filePath: filePath
        })
      }
    })
  })
}

/**
 * Upload multiple images concurrently (Promise.allSettled pattern -- ADR-007).
 * Single image failure does not block other uploads.
 *
 * @param {string[]} filePaths - Array of temporary file paths
 * @param {object} [options] - Optional configuration
 * @returns {Promise<Array<object>>} Array of results. Each element is either:
 *   - { status: 'fulfilled', value: { upload_id, expires_in, uploaded_at } }
 *   - { status: 'rejected',  reason: { code, message, filePath } }
 */
export function uploadImages(filePaths, options = {}) {
  if (!filePaths || filePaths.length === 0) {
    return Promise.resolve([])
  }

  const tasks = filePaths.map((fp) => uploadImage(fp, options))
  return Promise.allSettled(tasks)
}

/**
 * Check whether an upload_id has expired based on client-side upload time.
 *
 * @param {number} uploadedAt - The Date.now() timestamp when the image was uploaded
 * @param {number} [maxAgeMs=500000] - Max allowed age in milliseconds (default 500s)
 * @returns {boolean} true if the upload_id is considered expired
 */
export function isUploadIdExpired(uploadedAt, maxAgeMs) {
  if (maxAgeMs === undefined) {
    maxAgeMs = DEFAULT_TTL_MS
  }
  if (!uploadedAt || typeof uploadedAt !== 'number') {
    return true
  }
  return (Date.now() - uploadedAt) > maxAgeMs
}

export default { uploadImage, uploadImages, isUploadIdExpired }
