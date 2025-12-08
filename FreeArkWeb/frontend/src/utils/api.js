// API调用辅助函数

// 获取API基础URL
function getApiUrl(endpoint) {
  // 从环境变量获取API配置，或使用默认值
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
  // 环境变量中的baseUrl应该已经不包含/api前缀，直接拼接端点
  return `${baseUrl}${endpoint}`;
}

// 缓存CSRF token，避免频繁获取
let cachedCSRFToken = null;

// 获取CSRF Token函数
function getCSRFToken() {
  // 如果已有缓存的token，直接返回
  if (cachedCSRFToken) {
    return cachedCSRFToken;
  }
  
  // 从cookie中获取CSRF token
  const cookieParts = document.cookie.split('; ');
  for (let i = 0; i < cookieParts.length; i++) {
    const row = cookieParts[i];
    if (row.indexOf('csrftoken=') === 0) {
      const cookieValue = row.substring('csrftoken='.length);
      const decodedValue = decodeURIComponent(cookieValue);
      // 缓存token
      cachedCSRFToken = decodedValue;
      return decodedValue;
    }
  }
  
  return null;
}

// 确保获取CSRF Token的函数
async function ensureCSRFToken() {
  try {
    // 如果已有缓存的token，直接返回
    if (cachedCSRFToken) {
      return true;
    }
    
    // 使用环境变量中配置的API地址
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    
    // 规范化API基础URL，确保末尾没有斜杠
    const normalizedBaseUrl = apiBaseUrl.replace(/\/$/, '');
    
    // 调用get-csrf-token端点获取CSRF token
    const response = await fetch(`${normalizedBaseUrl}/api/get-csrf-token/`, {
      method: 'GET',
      credentials: 'include', // 确保包含cookies
      headers: {
        'Content-Type': 'application/json',
        'Origin': window.location.origin // 设置正确的origin头
      },
      mode: 'cors' // 显式设置为cors模式
    });
    
    if (response.ok) {
      // 重新获取token并缓存
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
      throw new Error(`API请求失败: ${response.status} ${response.statusText}`);
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
  
  // DELETE请求
  async delete(endpoint) {
    const response = await authenticatedFetch(endpoint, {
      method: 'DELETE'
    });
    
    if (!response.ok) {
      throw new Error(`API请求失败: ${response.status} ${response.statusText}`);
    }
    
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
  }
};

export default api;