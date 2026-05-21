// API调用辅助函数

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
  
  return fetch(getApiUrl(endpoint), mergedOptions);
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
      throw new Error(`API请求失败: ${response.status} ${response.statusText}`);
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
    }
  },

  // 暴露 clearCSRFToken，供特殊场景手动清除（如强制刷新 token）
  clearCSRFToken
};

export default api;