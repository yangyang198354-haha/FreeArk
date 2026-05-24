/**
 * FreeArk Skill — HTTP 客户端封装
 *
 * 职责：
 *   - 统一注入 Authorization: Token <agent-token> 头
 *   - URL 白名单校验（仅允许 127.0.0.1:8000，防止 SSRF）
 *   - 统一超时控制（Tier-1: 5000ms，Tier-2: 8000ms）
 *   - 统一错误处理：将 HTTP 错误码翻译为 Agent 友好的中文描述
 *   - Token 日志脱敏：日志中仅输出前 8 字符
 *
 * 安全约束（来自 MOD-SK-01, REQ-NFR-002）：
 *   - FREEARK_AGENT_TOKEN 从 process.env 读取，不硬编码，不打印完整值
 *   - 所有 HTTP 请求目标必须匹配 ALLOWED_HOST 白名单
 *   - 不在任何错误消息中回显 Token
 *
 * 文档引用: ARCH-LOBSTER-001 §3.3, MOD-SK-01, DECISIONS-LOBSTER-001 CONFIRM-1/CONFIRM-8
 */

'use strict';

const API_BASE = (process.env.FREEARK_API_BASE || 'http://127.0.0.1:8000').replace(/\/$/, '');
const AGENT_TOKEN = process.env.FREEARK_AGENT_TOKEN || '';

// 白名单：仅允许本地回环，防止 SSRF
const ALLOWED_HOSTS = ['127.0.0.1:8000', 'localhost:8000'];

const TIER1_TIMEOUT_MS = 5000;
const TIER2_TIMEOUT_MS = 8000;

/**
 * 验证目标 URL 是否在白名单内
 * @param {string} url
 * @returns {boolean}
 */
function isAllowedUrl(url) {
  try {
    const parsed = new URL(url);
    const hostPort = parsed.host; // 形如 "127.0.0.1:8000"
    return ALLOWED_HOSTS.some(h => hostPort === h);
  } catch {
    return false;
  }
}

/**
 * 将 HTTP 错误码翻译为 Agent 友好的中文错误对象
 * @param {number} status
 * @param {string} path
 * @returns {{error: string, status: number}}
 */
function translateHttpError(status, path) {
  const map = {
    401: `方舟龙虾的系统访问凭证已失效（401），请联系管理员重新配置 API Token。`,
    403: `此操作超出当前权限范围（403 Forbidden），请联系管理员确认账号权限。`,
    404: `未找到目标资源（404 Not Found）：${path}，请确认参数是否正确。`,
    429: `请求过于频繁（429），请稍后再试。`,
    500: `FreeArk 服务内部错误（500），请检查 freeark-backend 服务日志。`,
    502: `FreeArk 服务暂时不可达（502），请确认 Uvicorn 进程是否正常运行。`,
    503: `FreeArk 服务不可用（503），可能是 MQTT 通道异常，请检查 freeark-mqtt-consumer 状态。`,
  };
  return { error: map[status] || `FreeArk API 返回异常状态码（${status}），请检查服务日志。`, status };
}

/**
 * 核心 HTTP 请求函数
 *
 * @param {string} method - 'GET' | 'POST' | 'PUT' | 'DELETE'
 * @param {string} path - API 路径，如 '/api/devices/realtime-params/'
 * @param {object|null} body - POST/PUT 的请求体（将被 JSON 序列化）
 * @param {object} params - URL 查询参数（key-value）
 * @param {number} timeoutMs - 超时毫秒数
 * @returns {Promise<{ok: boolean, data?: any, error?: string, status?: number}>}
 */
async function request(method, path, body = null, params = {}, timeoutMs = TIER1_TIMEOUT_MS) {
  if (!AGENT_TOKEN) {
    return { ok: false, error: 'FREEARK_AGENT_TOKEN 环境变量未设置，无法调用 FreeArk API。', status: 0 };
  }

  // 构建完整 URL
  const url = new URL(API_BASE + path);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') {
      url.searchParams.append(k, String(v));
    }
  }

  const fullUrl = url.toString();

  // SSRF 防护：校验目标主机
  if (!isAllowedUrl(fullUrl)) {
    console.error(`[freeark-skill] SSRF 防护：拒绝请求非白名单地址 ${url.host}`);
    return { ok: false, error: 'Skill 安全限制：只允许访问 FreeArk 本地服务。', status: 0 };
  }

  const headers = {
    'Authorization': `Token ${AGENT_TOKEN}`,
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };

  const init = {
    method,
    headers,
    signal: AbortSignal.timeout(timeoutMs),
  };

  if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
    init.body = JSON.stringify(body);
  }

  try {
    const resp = await fetch(fullUrl, init);

    if (!resp.ok) {
      const errObj = translateHttpError(resp.status, path);
      console.warn(`[freeark-skill] API ${method} ${path} → ${resp.status}`);
      return { ok: false, ...errObj };
    }

    let data;
    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      data = await resp.json();
    } else {
      data = await resp.text();
    }

    return { ok: true, data, status: resp.status };

  } catch (err) {
    if (err.name === 'TimeoutError' || err.name === 'AbortError') {
      console.warn(`[freeark-skill] 请求超时: ${method} ${path} (${timeoutMs}ms)`);
      return { ok: false, error: `FreeArk API 请求超时（${timeoutMs / 1000}秒），请检查网络或服务状态。`, status: 0 };
    }
    console.error(`[freeark-skill] 请求异常: ${err.message}`);
    return { ok: false, error: `连接 FreeArk 服务失败：${err.message}，请确认 Uvicorn 进程正常运行（http://127.0.0.1:8000）。`, status: 0 };
  }
}

/**
 * Tier-1 GET 请求（5s 超时）
 */
async function get(path, params = {}) {
  return request('GET', path, null, params, TIER1_TIMEOUT_MS);
}

/**
 * Tier-2 POST 请求（8s 超时）
 */
async function post(path, body = {}, params = {}) {
  return request('POST', path, body, params, TIER2_TIMEOUT_MS);
}

/**
 * Tier-2 PUT 请求（8s 超时）
 */
async function put(path, body = {}, params = {}) {
  return request('PUT', path, body, params, TIER2_TIMEOUT_MS);
}

/**
 * 打印启动摘要（不输出完整 Token）
 */
function logStartup() {
  const tokenPreview = AGENT_TOKEN ? AGENT_TOKEN.substring(0, 8) + '...' : '(未设置)';
  console.log(`[freeark-skill] 初始化完成`);
  console.log(`[freeark-skill]   API_BASE: ${API_BASE}`);
  console.log(`[freeark-skill]   Token: ${tokenPreview}`);
}

module.exports = { get, post, put, logStartup, TIER1_TIMEOUT_MS, TIER2_TIMEOUT_MS };
