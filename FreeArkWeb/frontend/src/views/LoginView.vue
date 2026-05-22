<template>
  <!-- AC-UI-001-02: 全屏登录页 -->
  <div class="login-page">
    <!-- 背景层（§6.3 渐变兜底方案，PM 确认：渐变优先，图片可后续无痛替换）-->
    <!-- 若需换图片：只需修改 .login-bg 的 background-image，删除渐变背景并启用遮罩即可 -->
    <div class="login-bg">
      <!-- 遮罩：仅在有背景图时使用；纯渐变背景时已隐藏（.no-image 控制）-->
      <div class="login-bg-overlay"></div>
    </div>

    <!-- 内容层 -->
    <div class="login-card-wrapper">
      <!-- Logo + 平台名（§6.1）-->
      <div class="login-brand">
        <!-- SVG Logo —— 简洁方舟图形 -->
        <svg class="login-logo" width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="4" y="28" width="40" height="6" rx="3" fill="white"/>
          <path d="M8 28 L14 14 L24 10 L34 14 L40 28 Z" fill="rgba(255,255,255,0.85)"/>
          <rect x="22" y="10" width="4" height="18" rx="2" fill="white"/>
          <path d="M6 34 Q24 44 42 34" stroke="white" stroke-width="2" fill="none" stroke-linecap="round"/>
        </svg>
        <span class="login-brand-name">自由方舟能耗采集平台</span>
      </div>

      <!-- 登录卡片（AC-UI-001-02/03）-->
      <div class="login-card">
        <h2 class="login-card-title">用户登录</h2>

        <el-form :model="loginForm" :rules="loginRules" ref="loginFormRef" label-position="top">
          <el-form-item prop="username">
            <el-input
              v-model="loginForm.username"
              placeholder="请输入用户名"
              size="large"
              :prefix-icon="UserIcon"
              autocomplete="username"
            />
          </el-form-item>

          <el-form-item prop="password">
            <el-input
              v-model="loginForm.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              :prefix-icon="LockIcon"
              show-password
              autocomplete="current-password"
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <div v-if="error" class="login-error-msg">
            <el-icon><Warning /></el-icon>
            {{ error }}
          </div>

          <el-form-item style="margin-bottom: 0;">
            <el-button
              type="primary"
              class="login-btn"
              @click="handleLogin"
              :loading="loading"
              size="large"
            >
              {{ loading ? '登录中...' : '登录' }}
            </el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, markRaw } from 'vue'
import { User, Lock, Warning } from '@element-plus/icons-vue'

export default {
  name: 'LoginView',
  components: { Warning },
  setup() {
    // markRaw 避免 icon 被响应式代理，提升性能
    const UserIcon = markRaw(User)
    const LockIcon = markRaw(Lock)
    return { UserIcon, LockIcon }
  },
  data() {
    return {
      loginForm: {
        username: '',
        password: ''
      },
      loginRules: {
        username: [
          { required: true, message: '请输入用户名', trigger: 'blur' }
        ],
        password: [
          { required: true, message: '请输入密码', trigger: 'blur' }
        ]
      },
      loading: false,
      error: ''
    }
  },
  methods: {
    async handleLogin() {
      this.$refs.loginFormRef.validate(async (valid) => {
        if (valid) {
          this.loading = true
          this.error = ''
          try {
            const baseUrl = import.meta.env.VITE_API_BASE_URL ||
              (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000')
            const loginUrl = `${baseUrl}/api/auth/login/`

            const resp = await fetch(loginUrl, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              credentials: 'include',
              body: JSON.stringify(this.loginForm)
            })

            if (!resp.ok) {
              const errData = await resp.json().catch(() => ({}))
              throw { response: { data: errData } }
            }

            const data = await resp.json()

            if (data.token) {
              localStorage.setItem('userToken', data.token)
              localStorage.setItem('isAuthenticated', 'true')
              const secure = window.location.protocol === 'https:'
              let cookieString = `auth_token=${encodeURIComponent(data.token)}; path=/; max-age=86400; SameSite=Lax`
              if (secure) cookieString += '; Secure'
              document.cookie = cookieString
              this.$router.push('/')
            }
          } catch (error) {
            let errorMessage = '登录失败，请检查用户名和密码'
            if (error.response) {
              errorMessage = error.response.data?.non_field_errors?.[0] ||
                             error.response.data?.detail ||
                             errorMessage
            } else if (error.message && (
              error.message.includes('NetworkError') ||
              error.message.includes('Failed to fetch')
            )) {
              errorMessage = '网络连接异常，请检查您的网络'
            }
            this.error = errorMessage
          } finally {
            this.loading = false
          }
        }
      })
    }
  }
}
</script>

<style scoped>
/* ---- 全屏容器（§6.2）---- */
.login-page {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ---- 背景层（§6.3 渐变兜底）----
   设计约束（PM 确认）：
   - 当前为 CSS 渐变兜底，后续换图片只需：
     1. 在 background-image 加 url('/assets/login-bg.jpg')
     2. 移除渐变 background 属性
     3. 删除 .login-bg-overlay { display: none } 一行，启用遮罩
*/
.login-bg {
  position: absolute;
  inset: 0;
  /* 渐变兜底背景（§6.3）*/
  background: linear-gradient(
    135deg,
    #0F1C2E 0%,
    #1A2A4A 40%,
    #0D2137 70%,
    #0F1C2E 100%
  );
  /* 预留图片替换槽：background-image: url('/assets/login-bg.jpg'); background-size: cover; */
}

/* 渐变背景下遮罩不需要（§6.3 注释：纯深色渐变已足够对比）*/
.login-bg-overlay {
  display: none;
}

/* ---- 内容层（§6.2 .login-card-wrapper）---- */
.login-card-wrapper {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-6);
  width: 100%;
  max-width: 420px;
  padding: var(--space-5);
}

/* ---- Logo + 平台名（§6.2 .login-brand）---- */
.login-brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  color: var(--color-text-inverse);
}

.login-logo {
  flex-shrink: 0;
  filter: drop-shadow(0 2px 8px rgba(255, 255, 255, 0.2));
}

.login-brand-name {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-inverse);
  white-space: nowrap;
}

/* ---- 登录卡片（§6.2 .login-card）---- */
.login-card {
  width: 100%;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: var(--radius-xl);
  padding: var(--space-8) var(--space-8) var(--space-6);
  box-shadow: var(--shadow-lg);

  /* AC-UI-001-03: 入场动画（500ms ease-out，translateY 20px→0）*/
  animation: loginCardEnter 500ms ease-out both;
}

@keyframes loginCardEnter {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 卡片标题 */
.login-card-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0 0 var(--space-6) 0;
  text-align: center;
}

/* AC-UI-001-03: 输入框 focus 过渡（§6.2）*/
.login-card :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--color-border-focus) inset;
  transition: box-shadow 150ms ease-in-out;
}

/* el-form-item label 间距 */
.login-card :deep(.el-form-item) {
  margin-bottom: var(--space-5);
}

/* 错误提示 */
.login-error-msg {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-4);
  padding: var(--space-2) var(--space-3);
  background-color: rgba(239, 68, 68, 0.08);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(239, 68, 68, 0.2);
}

/* ---- 登录按钮（§6.2 .login-btn）---- */
.login-btn {
  width: 100%;
  height: 44px;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  border-radius: var(--radius-base);
  transition: background-color 150ms ease-in-out, transform 150ms ease-in-out;
}

.login-btn:active {
  transform: scale(0.98);
}
</style>
