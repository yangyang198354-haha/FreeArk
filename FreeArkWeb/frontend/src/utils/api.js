// API调用辅助函数

// REQ-AUTH-003 (v0.9.0): router 实例，用于 authenticatedFetch 中 401 统一跳转。
// router/index.js 不 import api.js（已确认），无循环依赖，可直接顶层 import。
// 使用懒加载 getter 是保险措施：若某些 HMR 热更新场景中模块还未就绪，
// 延迟到函数调用时再读取，确保 router 已初始化完成。
import _routerModule from '../router/index.js';
function getRouter() {
  return _routerModule;
}

// 清除认证 cookie（与 clearCSRFToken 对称；v0.9.0 新增）
function clearAuthCookie() {
  document.cookie = 'auth_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
}

// 获取API基础URL
function getApiUrl(endpoint) {
  // 优先使用环境变量；生产环境留空时取当前页面 origin，
  // API 请求走同源 Nginx 代理，LAN/外网均正常；开发时 fallback 到 localhost:8000
  const baseUrl = import.meta.env.VITE_API_BASE_URL
    || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000');
  return `${baseUrl}${endpoint}`;
}

// 缓存CSRF token，避免频繁调用 /api/get-csrf-token/
// 注意：仅由 ensureCSRFToken() 负责写入此缓存。
// 登出时必须通过 clearCSRFToken() 将其重置，否则 Django rotate_token()
// 产生的新 token 与此缓存不一致，导致后续请求 CSRF 验证失败。
let cachedCSRFToken = null;

// 会话过期提示去重标志（v1.0.x 修复：超时弹窗重复）
// 会话超时时页面上常有多个并发请求同时收到 401，每个 authenticatedFetch
// 实例若各自 ElMessage.warning 会弹出 N 条相同提示。此模块级标志保证
// 一次过期周期内只弹一次。登录成功后须调用 resetSessionExpiredFlag() 复位，
// 使下一次会话过期能再次提示。
// 注意：不可在 clearCSRFToken() 中复位——该函数在 401 处理内部即被调用，
// 复位会让并发请求各自重新弹窗，反而破坏去重。
let _sessionExpiredShown = false;

// 复位会话过期提示标志（登录成功时调用）
function resetSessionExpiredFlag() {
  _sessionExpiredShown = false;
}

// 清除 CSRF token 缓存（供 logout 时调用）
// BUG-CSRF-001 修复：登出后重置缓存，防止下次登录携带过期 token
function clearCSRFToken() {
  cachedCSRFToken = null;
}

// 从 cookie 直接读取 CSRF token（不使用内存缓存，保证读到最新值）
// BUG-CSRF-001 修复：去除内部缓存短路，确保 Django rotate_token() 后能感知新 token
function getCSRFToken() {
  const cookieParts = document.cookie.split('; ');
  for (let i = 0; i < cookieParts.length; i++) {
    const row = cookieParts[i];
    if (row.indexOf('csrftoken=') === 0) {
      const cookieValue = row.substring('csrftoken='.length);
      return decodeURIComponent(cookieValue);
    }
  }
  return null;
}

// 确保 CSRF token 已就绪
// 若 cookie 中已有 token（例如 Django login() 刚写入），直接使用，无需网络请求。
// 若 cookie 中没有，才调用 /api/get-csrf-token/ 触发后端写入 cookie。
// BUG-CSRF-001 修复：不再依赖 cachedCSRFToken 的短路判断，
// 改为每次先尝试从 cookie 读取（getCSRFToken() 已去除内部缓存）。
async function ensureCSRFToken() {
  try {
    // 优先从 cookie 直接读取（Django login() 会通过 Set-Cookie 写入最新 token）
    const tokenFromCookie = getCSRFToken();
    if (tokenFromCookie) {
      // 更新内存缓存，供本次请求链使用
      cachedCSRFToken = tokenFromCookie;
      return true;
    }

    // cookie 中没有 token，调用后端接口触发写入
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL
      || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000');
    const normalizedBaseUrl = apiBaseUrl.replace(/\/$/, '');

    const response = await fetch(`${normalizedBaseUrl}/api/get-csrf-token/`, {
      method: 'GET',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'Origin': window.location.origin
      },
      mode: 'cors'
    });

    if (response.ok) {
      // 后端已通过 Set-Cookie 写入 csrftoken，从 cookie 重新读取
      cachedCSRFToken = getCSRFToken();
      return true;
    } else {
      console.error('获取CSRF token失败:', response.status);
      return false;
    }
  } catch (error) {
    console.error('获取CSRF token过程出错:', error);
    return false;
  }
}

// 从cookie或localStorage获取认证token
function getAuthToken() {
  // 首先尝试从cookie获取
  const cookieValue = document.cookie
    .split('; ')
    .find(row => row.startsWith('auth_token='))
    ?.split('=')[1];
  
  if (cookieValue) {
    return decodeURIComponent(cookieValue);
  }
  
  // 如果cookie中没有，尝试从localStorage获取
  return localStorage.getItem('userToken') || null;
}

// 带认证的fetch封装
async function authenticatedFetch(endpoint, options = {}) {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('未登录或登录已过期');
  }
  
  // 确保获取CSRF token
  let csrfToken = getCSRFToken();
  if (!csrfToken) {
    const csrfTokenObtained = await ensureCSRFToken();
    if (!csrfTokenObtained) {
      throw new Error('无法获取必要的安全令牌，请刷新页面重试');
    }
    // 重新获取CSRF token
    csrfToken = getCSRFToken();
  }
  
  const defaultOptions = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Token ${token}`,
      'X-CSRFToken': csrfToken
    },
    credentials: 'include' // 确保包含cookies
  };
  
  const mergedOptions = {
    ...defaultOptions,
    ...options,
    headers: {
      ...defaultOptions.headers,
      ...options.headers
    }
  };

  // perf-P0：请求超时保护。后端单 worker 下若某接口 hang 住，原生 fetch 无超时会
  // 让调用方的 loading 永不结束（页面"一直转圈"）。此处加 15s AbortController 兜底，
  // 超时后 fetch 抛错 → 调用方 catch 能正常关闭 loading。调用方自带 signal 时不覆盖。
  const DEFAULT_TIMEOUT_MS = 15000;
  let _timeoutId = null;
  if (!mergedOptions.signal) {
    const controller = new AbortController();
    mergedOptions.signal = controller.signal;
    _timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  }

  let response;
  try {
    response = await fetch(getApiUrl(endpoint), mergedOptions);
  } catch (err) {
    if (err && err.name === 'AbortError') {
      throw new Error('请求超时，请稍后重试');
    }
    throw err;
  } finally {
    if (_timeoutId) clearTimeout(_timeoutId);
  }

  // REQ-AUTH-003 (v0.9.0): 统一拦截 401，清理本地凭证并跳转登录页
  if (response.status === 401) {
    // 防止循环重定向：已在登录页时跳过弹窗和路由跳转
    let isOnLoginPage = false;
    try {
      const router = getRouter();
      isOnLoginPage = router.currentRoute.value.name === 'Login';
    } catch (_) {
      // router 不可用时降级
    }

    // 清理本地凭证
    localStorage.removeItem('userToken');
    clearAuthCookie();
    clearCSRFToken();

    if (!isOnLoginPage) {
      // 展示过期提示（动态导入，避免 api.js 对 element-plus 产生静态依赖）
      // 去重：并发请求同时收到 401 时，仅首个触发弹窗，其余跳过
      if (!_sessionExpiredShown) {
        _sessionExpiredShown = true;
        try {
          const { ElMessage } = await import('element-plus');
          ElMessage.warning('会话已过期，请重新登录');
        } catch (_) {
          // ElMessage 不可用时静默继续，不阻断跳转
        }
      }
      try {
        const router = getRouter();
        router.replace({ name: 'Login' });
      } catch (_) {
        // router 不可用时降级为原生跳转
        window.location.href = '/login';
      }
    }

    // 抛出特定错误，使调用方 catch 块可识别（无需各自再处理 401 跳转）
    throw new Error('SESSION_EXPIRED');
  }

  return response;
}

// 封装常用的API请求方法
const api = {
  // GET请求
  async get(endpoint, params = {}) {
    // 构建查询参数
    const queryParams = new URLSearchParams(params);
    const url = `${endpoint}${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
    
    const response = await authenticatedFetch(url, {
      method: 'GET'
    });
    
    if (!response.ok) {
      if (response.status === 401) {
        throw new Error(`认证失败(401): Token 无效或已过期，请重新登录`);
      }
      throw new Error(`API请求失败: ${response.status} ${response.statusText}`);
    }

    return response.json();
  },

  // POST请求
  async post(endpoint, data = {}) {
    const response = await authenticatedFetch(endpoint, {
      method: 'POST',
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      // 尝试解析后端 JSON 错误体（{error: "..."}）以便上层展示具体原因
      let backendMsg = '';
      try {
        const body = await response.clone().json();
        if (body && (body.error || body.message)) {
          backendMsg = body.error || body.message;
        }
      } catch (_) { /* body 非 JSON 或为空 */ }
      const suffix = backendMsg ? ` - ${backendMsg}` : '';
      throw new Error(`API请求失败: ${response.status} ${response.statusText}${suffix}`);
    }

    return response.json();
  },
  
  // PUT请求
  async put(endpoint, data = {}) {
    const response = await authenticatedFetch(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      // 尝试解析后端 JSON 错误体（{error: "..."}）以便上层展示具体原因
      let backendMsg = '';
      try {
        const body = await response.clone().json();
        if (body && (body.error || body.message)) {
          backendMsg = body.error || body.message;
        }
      } catch (_) { /* body 非 JSON 或为空 */ }
      const suffix = backendMsg ? ` - ${backendMsg}` : '';
      throw new Error(`API请求失败: ${response.status} ${response.statusText}${suffix}`);
    }

    return response.json();
  },
  
  // PATCH请求
  async patch(endpoint, data = {}) {
    const response = await authenticatedFetch(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(data)
    });

    if (!response.ok) {
      throw new Error(`API请求失败: ${response.status} ${response.statusText}`);
    }

    return response.json();
  },

  // DELETE请求
  async delete(endpoint) {
    const response = await authenticatedFetch(endpoint, {
      method: 'DELETE'
    });

    if (!response.ok) {
      throw new Error(`API请求失败: ${response.status} ${response.statusText}`);
    }

    // 204 No Content 无响应体
    if (response.status === 204) return null;
    return response.json();
  },
  
  // 导出为Excel
  async exportToExcel(endpoint, params = {}, filename) {
    // 构建查询参数
    const queryParams = new URLSearchParams(params);
    const url = `${endpoint}${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
    
    const response = await authenticatedFetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      }
    });
    
    if (!response.ok) {
      throw new Error(`API请求失败: ${response.status} ${response.statusText}`);
    }
    
    const blob = await response.blob();
    const urlObject = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = urlObject;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(urlObject);
  },

  // 登出：调用后端销毁 session/Token，并清除本地 CSRF 缓存
  // BUG-CSRF-001 修复：统一由此方法处理登出，调用方无需关心缓存细节
  // v0.9.0 追加：finally 块中同步清理 userToken 和 auth_token cookie
  async logout() {
    try {
      // 通知后端销毁 session 和 Token
      await authenticatedFetch('/api/auth/logout/', { method: 'POST' });
    } catch (e) {
      // 后端登出失败（如 token 已失效）时仍继续本地清理，不阻断登出流程
      console.warn('后端登出请求失败，继续本地清理:', e.message);
    } finally {
      // 清除内存中缓存的 CSRF token
      clearCSRFToken();
      // v0.9.0: 清除认证凭证（与 401 拦截逻辑对称）
      localStorage.removeItem('userToken');
      clearAuthCookie();
    }
  },

  // 暴露 clearCSRFToken，供特殊场景手动清除（如强制刷新 token）
  clearCSRFToken,
  // v0.9.0: 暴露 clearAuthCookie，供特殊场景使用
  clearAuthCookie,
  // v1.0.x: 暴露会话过期提示复位，供登录成功后调用
  resetSessionExpiredFlag,

  // MOD-FE-03 IFC-FE-03-01: 获取会话列表（语义封装，内部调用 api.get）
  getSessionList(page, pageSize) {
    if (page === undefined) page = 1;
    if (pageSize === undefined) pageSize = 20;
    return this.get('/api/memory/me/', { page: page, page_size: pageSize });
  },

  // MOD-FE-03 IFC-FE-03-02: 软删除指定会话（语义封装，内部调用 api.delete）
  deleteSession(sessionKey) {
    return this.delete(`/api/memory/session/${sessionKey}/`);
  },

  // MOD-FE-API IFC-FE-API-001: 获取会话历史消息（最近 40 条，升序）
  // 参数：sessionKey — 完整 UUID 字符串
  // 返回：{ session_key, messages: [{role, content, created_at}], total }
  // 异常：网络失败或 HTTP 非 200 时抛出 Error；SESSION_EXPIRED 由 authenticatedFetch 统一处理
  getSessionHistory(sessionKey) {
    return this.get(`/api/memory/session/${sessionKey}/history/`);
  },
};

export default api;

// ── v1.4.1 新增（IFC-141-1101，MOD-141-11）────────────────────────────────────
// fetchRagImage：取 RAG 图片字节，返回 Blob，供调用方调用 URL.createObjectURL
//
// 设计决策（DEV-001）：
//   不能用 api.get()，因为 api.get() 内部调用 response.json()；
//   图片响应体是 binary，不能解析为 JSON（会抛错）。
//   必须直接使用 authenticatedFetch，手动调用 response.blob()。
//
// 认证：authenticatedFetch 自动携带 Authorization: Token <xxx> 头（REQ-NFR-004）。
// 前端必须用本函数取图（禁止裸 import axios，见前端认证陷阱记录）。
//
// 参数：imageId — integer，来自 stream_end.related_images[i].image_id
// 返回：Promise<Blob>（成功）
// 异常：404/非 200 时抛出 Error；网络失败或 SESSION_EXPIRED 由 authenticatedFetch 统一处理
export async function fetchRagImage(imageId) {
  const response = await authenticatedFetch(`/api/rag/images/${imageId}/`, {
    method: 'GET',
  });
  if (!response.ok) {
    throw new Error(`fetchRagImage: HTTP ${response.status} for image_id=${imageId}`);
  }
  return response.blob();
}

// ── v1.5.0 新增（IFC-MQ-01-001，MOD-MQ-01）──────────────────────────────────
// uploadChatImage：图片预上传，返回 { upload_id, expires_in }
//
// 设计决策（C-010 硬约束）：
//   必须通过 authenticatedFetch 封装调用，禁止裸 axios（见 freeark-frontend-bare-axios-session-trap）。
//   不使用 api.post()——该方法设置 Content-Type: application/json + body: JSON.stringify，
//   不兼容 multipart/form-data；需手动构造 FormData 并让 fetch 自动设置边界。
//
// 安全约束（SC-001/SC-002）：
//   图片字节以 Blob 对象通过 multipart/form-data 上传，不做 base64 编码，
//   不出现在任何 console.log、URL、WS 帧中。
//
// 参数：file — File 或 Blob 对象（前端 Canvas 压缩后的输出）
// 返回：Promise<{ upload_id: string, expires_in: number }>
// 异常：HTTP 非 200/413/400/503 时抛出 Error（含状态码）；SESSION_EXPIRED 由 authenticatedFetch 统一处理
export async function uploadChatImage(file) {
  const formData = new FormData();
  formData.append('image', file);

  // authenticatedFetch 默认会在 headers 中设置 'Content-Type': 'application/json'，
  // 但 multipart/form-data 需要 fetch 自动计算 boundary，不能手动设置 Content-Type。
  // 解决方案：先调用 authenticatedFetch，再在发出前删除 Content-Type 头。
  // 实现：使用带自定义 headers 的方式，传入对象后删除 Content-Type 键。
  //
  // 注意：authenticatedFetch 的 mergedOptions.headers 是普通对象（不是 Headers 实例），
  // 可以直接 delete。但 authenticatedFetch 内部已经完成合并，需要在外层处理。
  //
  // 最简洁方案：直接构造带认证头的 fetch 请求（不经 authenticatedFetch 的 Content-Type 层）。
  // authenticatedFetch 的核心价值是：Bearer Token + CSRF + 401 统一处理。
  // 此处通过 authenticatedFetch 获取认证信息，再单独构造请求。
  //
  // 实际上，可以借助 authenticatedFetch 的 headers 覆盖机制：
  // 当 options.headers['Content-Type'] 被设为 null/空字符串时，merged header 仍存在该键。
  // 最终 fetch 会因 Content-Type 不正确而出错（boundary 丢失）。
  //
  // 正确做法：让 authenticatedFetch 处理认证，但 body 为 FormData 且不手动设 Content-Type。
  // authenticatedFetch 展开 headers 后调用 fetch，此时 Content-Type: 'application/json' 存在。
  // 浏览器看到 Content-Type: application/json + FormData body 不会自动改写。
  //
  // 最终选择：完全手动构造认证 fetch，复用 getAuthToken/getCSRFToken 私有函数。
  // 但这些函数未导出。因此采用"传递特殊标记让 authenticatedFetch 跳过 Content-Type"的方式：
  // 传入一个特殊 _skipContentType 字段，在 authenticatedFetch 中处理。
  //
  // 鉴于不应修改 authenticatedFetch 核心逻辑，改为直接读取 token 并调用 fetch：

  const token = localStorage.getItem('userToken')
    || (document.cookie.split('; ').find(r => r.startsWith('auth_token=')) || '').split('=')[1]
    || null;

  if (!token) throw new Error('未登录或登录已过期');

  // 获取 CSRF token（复用 cookie 读取逻辑）
  let csrfToken = null;
  const cookieParts = document.cookie.split('; ');
  for (const part of cookieParts) {
    if (part.startsWith('csrftoken=')) {
      csrfToken = decodeURIComponent(part.split('=')[1]);
      break;
    }
  }

  // 构造 fetch 请求（不设 Content-Type，让 FormData 自动计算 boundary）
  const baseUrl = import.meta.env.VITE_API_BASE_URL
    || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000');

  const headers = {
    'Authorization': `Token ${token}`,
  };
  if (csrfToken) headers['X-CSRFToken'] = csrfToken;

  const response = await fetch(`${baseUrl}/api/chat/image-upload/`, {
    method: 'POST',
    headers,
    body: formData,
    credentials: 'include',
  });

  // 统一 401 处理（SESSION_EXPIRED 语义对齐）
  if (response.status === 401) {
    localStorage.removeItem('userToken');
    throw new Error('SESSION_EXPIRED');
  }

  if (!response.ok) {
    let errorMsg = `图片上传失败（HTTP ${response.status}）`;
    try {
      const body = await response.clone().json();
      if (body && body.error) errorMsg = body.error;
    } catch (_) { /* 响应体非 JSON，使用默认消息 */ }
    throw new Error(errorMsg);
  }

  return response.json();
}

// ── v1.9.0 新增（IFC-MI-01-001，MOD-MI-01）──────────────────────────────────
// uploadChatImages：并发批量上传多张图片，返回成功上传的 upload_id 列表。
//
// 设计决策（ADR-MI-002：并发 POST，Promise.allSettled）：
//   - 并发上传将5张图的等待时间从 O(N) 降至 O(1)（最慢一张）
//   - Promise.allSettled 保证全部 settled，部分失败不阻断（容错优先，OQ-MI-001 方案A）
//   - 失败图片记录到 console.warn，不抛出，由调用方处理
//
// 安全约束（SC-001/SC-002/C-MI-005）：
//   - 每张图通过 uploadChatImage 上传（authenticatedFetch，禁止裸 axios）
//   - upload_id 不含图片内容，不出现在 WS 帧或日志中
//
// 参数：files — File[] 或 Blob[] 数组（前端 Canvas 压缩后的输出）
// 返回：Promise<string[]>（成功上传的 upload_id 列表，长度可能 < files.length）
// 异常：不抛出（allSettled 保证全部 settled，失败项通过 console.warn 记录）
export async function uploadChatImages(files) {
  if (!files || files.length === 0) return [];

  const results = await Promise.allSettled(
    files.map(file => uploadChatImage(file))
  );

  const uploadIds = [];
  const failures = [];
  results.forEach((result, index) => {
    if (result.status === 'fulfilled') {
      uploadIds.push(result.value.upload_id);
    } else {
      failures.push({ index, reason: result.reason && result.reason.message });
    }
  });

  if (failures.length > 0) {
    // 安全约束：日志中不含图片内容，只记录失败索引和原因
    console.warn(
      `uploadChatImages: ${failures.length}/${files.length} 张图片上传失败`,
      failures.map(f => `[${f.index}] ${f.reason}`).join(', ')
    );
  }

  return uploadIds; // 仅返回成功的 upload_id 列表
}