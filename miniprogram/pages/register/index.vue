<!--
  @module MOD-PAGE-REGISTER
  @description 业主注册页（v1.8.0，REQ-AUTH-001）
    - 账号密码注册，复用 web 注册逻辑（后端 UserRegistrationSerializer，role 强制 user）
    - 调用 api.miniappRegister({username,password,password2,email}) → POST /api/miniapp/auth/register/
    - 成功(201)直接保存 token+user 并进入首页（注册即登录）
    - 字段校验：用户名/密码非空，两次密码一致；后端 400 错误体回显
  视觉规格（赛博朋克完整版，对齐登录页）：
    深空底 #05070f + 霓虹网格/扫描线/CRT 纹理 + HUD 角标 + 渐变注册按钮。
    px → rpx 按 2× 换算，字体仅声明并回退系统栈（小程序域名白名单不稳）。
-->
<template>
  <view class="register-page">

    <!-- ===== 背景装饰层 ===== -->
    <view class="bg-base"></view>
    <view class="bg-grid"></view>
    <view class="bg-blob"></view>

    <!-- ===== 顶部特效层（扫描线/CRT/暗角/HUD角标）===== -->
    <template v-if="fxOn">
      <view class="blob blob-1"></view>
      <view class="blob blob-2"></view>
      <view class="crt-lines"></view>
      <view class="scanline"></view>
      <view class="vignette"></view>

      <!-- HUD 角标 -->
      <view class="hud hud-tl">
        <view>SYS://ARK.OS</view>
        <view>v2.6.0 // SECURE</view>
      </view>
      <view class="hud hud-tr">
        <view>NODE 0x7F</view>
        <view>LAT 31.2 LON 121.4</view>
      </view>
      <view class="hud hud-bl"><view class="hud-dot"></view><text>LINK ONLINE</text></view>
      <view class="hud hud-br hud-purple">ENC // AES-256</view>
    </template>

    <!-- 状态栏占位（custom 导航） -->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer"></view>

    <!-- header -->
    <view class="header">
      <view class="back-btn" @tap="goBack"></view>
      <text class="header-title">注册账号</text>
    </view>

    <!-- ===== 前景内容列 ===== -->
    <view class="content">

      <!-- 标题 -->
      <view class="tagline">方舟座舱<text class="tag-dot">·</text>注册</view>
      <view class="subtitle">JOIN THE ARK</view>

      <!-- ===== 表单卡 ===== -->
      <view class="card">
        <view class="cb cb-tl"></view>
        <view class="cb cb-tr"></view>
        <view class="cb cb-bl"></view>
        <view class="cb cb-br"></view>

        <!-- 账号 -->
        <view class="field-label"><text class="gt">&gt;</text>账号</view>
        <view class="field" :class="{ focused: focusField === 'user' }">
          <input
            class="field-input"
            type="text"
            v-model="username"
            placeholder="请设置账号"
            placeholder-class="field-ph"
            :disabled="loading"
            @focus="focusField = 'user'"
            @blur="focusField = ''"
          />
        </view>

        <!-- 邮箱（选填） -->
        <view class="field-label field-label-next"><text class="gt">&gt;</text>邮箱（选填）</view>
        <view class="field" :class="{ focused: focusField === 'email' }">
          <input
            class="field-input"
            type="text"
            v-model="email"
            placeholder="请输入邮箱"
            placeholder-class="field-ph"
            :disabled="loading"
            @focus="focusField = 'email'"
            @blur="focusField = ''"
          />
        </view>

        <!-- 密码 -->
        <view class="field-label field-label-next"><text class="gt">&gt;</text>密码</view>
        <view class="field" :class="{ focused: focusField === 'pwd' }">
          <input
            class="field-input field-input-pwd"
            type="text"
            :password="!showPwd"
            v-model="password"
            placeholder="请设置密码"
            placeholder-class="field-ph"
            :disabled="loading"
            @focus="focusField = 'pwd'"
            @blur="focusField = ''"
          />
          <view class="eye" :class="showPwd ? 'eye-on' : 'eye-off'" @tap="showPwd = !showPwd"></view>
        </view>

        <!-- 确认密码 -->
        <view class="field-label field-label-next"><text class="gt">&gt;</text>确认密码</view>
        <view class="field" :class="{ focused: focusField === 'pwd2' }">
          <input
            class="field-input field-input-pwd"
            type="text"
            :password="!showPwd2"
            v-model="password2"
            placeholder="请再次输入密码"
            placeholder-class="field-ph"
            :disabled="loading"
            @focus="focusField = 'pwd2'"
            @blur="focusField = ''"
          />
          <view class="eye" :class="showPwd2 ? 'eye-on' : 'eye-off'" @tap="showPwd2 = !showPwd2"></view>
        </view>

        <!-- 注册按钮 -->
        <button
          class="register-btn"
          :disabled="loading"
          @tap="handleRegister"
        >
          <view v-if="fxOn" class="sheen"></view>
          <view v-if="loading" class="btn-loading">
            <view class="spinner"></view>
            <text class="btn-loading-txt">注册中</text>
          </view>
          <text v-else class="btn-txt">注 册</text>
        </button>

        <!-- 返回登录 -->
        <view class="back-link">已有账号？<text class="back-link-highlight" @tap="goBack">返回登录</text></view>
      </view>

    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'

const authStore = useAuthStore()
const username = ref('')
const email = ref('')
const password = ref('')
const password2 = ref('')
const loading = ref(false)
const showPwd = ref(false)
const showPwd2 = ref(false)
const focusField = ref('')
const fxOn = ref(true)

const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = sysInfo.statusBarHeight || 20

async function handleRegister() {
  if (!username.value.trim()) {
    uni.showToast({ title: '请输入账号', icon: 'none' })
    return
  }
  if (!password.value || !password2.value) {
    uni.showToast({ title: '请输入密码', icon: 'none' })
    return
  }
  if (password.value !== password2.value) {
    uni.showToast({ title: '两次密码不一致', icon: 'none' })
    return
  }
  loading.value = true
  try {
    const payload = {
      username: username.value.trim(),
      password: password.value,
      password2: password2.value,
    }
    if (email.value.trim()) payload.email = email.value.trim()
    const res = await api.miniappRegister(payload)
    if (res && res.token) {
      // 注册即登录：保存 token + user（role 后端强制 user）
      authStore.login(res.token, res.user)
      uni.reLaunch({ url: '/pages/home/index' })
    } else {
      throw new Error('注册失败')
    }
  } catch (err) {
    // 后端 400 返回字段级错误（如 {username:["已存在"]}），http.js 只透传 HTTP 状态，
    // 这里给出通用提示（用户名占用是最常见原因）。
    const msg = err.message && err.message.includes('HTTP 400')
      ? '注册失败：账号可能已被占用或密码过弱'
      : '注册失败，请检查网络'
    uni.showToast({ title: msg, icon: 'none', duration: 2500 })
  } finally {
    loading.value = false
  }
}

function goBack() {
  uni.navigateBack({ fail: () => uni.reLaunch({ url: '/pages/login/index' }) })
}
</script>

<style scoped>
.register-page {
  position: relative;
  height: 100vh;
  width: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #05070f;
  font-family: 'Noto Sans SC', -apple-system, sans-serif;
}

/* ── 背景基底 ─────────────────────────────────────────────────────────── */
.bg-base, .bg-grid, .bg-blob { position: absolute; pointer-events: none; }
.bg-base {
  inset: 0; z-index: 0;
  background:
    radial-gradient(90% 45% at 18% 0%, rgba(101,55,180,0.32), transparent 55%),
    radial-gradient(80% 40% at 100% 4%, rgba(20,180,170,0.22), transparent 55%),
    linear-gradient(180deg, #0b0a1a, #07101c 60%, #050811);
}
.bg-grid {
  inset: 0; z-index: 0;
  background-image:
    linear-gradient(rgba(56,230,224,0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56,230,224,0.06) 1px, transparent 1px);
  background-size: 80rpx 80rpx;
  -webkit-mask-image: linear-gradient(180deg, #000, transparent 55%);
  mask-image: linear-gradient(180deg, #000, transparent 55%);
  animation: ark-grid 3.6s linear infinite;
}
.bg-blob {
  width: 400rpx; height: 400rpx; left: -120rpx; top: 180rpx; border-radius: 50%; z-index: 0;
  background: radial-gradient(circle, rgba(139,92,246,0.22), transparent 70%);
  filter: blur(8px);
  animation: ark-float 16s ease-in-out infinite;
}

.status-spacer { position: relative; z-index: 5; flex: 0 0 auto; }

/* ── header ───────────────────────────────────────────────────────────── */
.header {
  position: relative; z-index: 5; flex: 0 0 auto;
  height: 92rpx; width: 100%;
  display: flex; align-items: center; justify-content: center;
}
.back-btn {
  position: absolute; left: 24rpx;
  width: 44rpx; height: 44rpx;
  background-repeat: no-repeat; background-position: center; background-size: 44rpx 44rpx;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23eaf6ff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M15 5l-7 7 7 7'/%3E%3C/svg%3E");
}
.header-title {
  font-size: 34rpx; font-weight: 700; letter-spacing: 8rpx; color: #f4fbff;
  text-shadow: 0 0 12px rgba(56,230,224,0.5);
}

/* ── 光晕团 ───────────────────────────────────────────────────────────── */
.blob { position: absolute; border-radius: 50%; filter: blur(16rpx); z-index: 0; pointer-events: none; }
.blob-1 {
  width: 440rpx; height: 440rpx; left: -120rpx; top: 240rpx;
  background: radial-gradient(circle, rgba(139,92,246,0.35), transparent 70%);
  animation: ark-float 9s ease-in-out infinite;
}
.blob-2 {
  width: 400rpx; height: 400rpx; right: -100rpx; top: 720rpx;
  background: radial-gradient(circle, rgba(47,244,224,0.28), transparent 70%);
  animation: ark-float 11s ease-in-out infinite reverse;
}

/* ── CRT 扫描纹理 ──────────────────────────────────────────────────────── */
.crt-lines {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  background: repeating-linear-gradient(0deg, rgba(0,0,0,0) 0, rgba(0,0,0,0) 4rpx, rgba(0,0,0,0.16) 6rpx, rgba(0,0,0,0) 8rpx);
}
/* ── 扫描线 ───────────────────────────────────────────────────────────── */
.scanline {
  position: absolute; left: 0; right: 0; top: 0; height: 240rpx; z-index: 1; pointer-events: none;
  background: linear-gradient(180deg, transparent, rgba(56,230,224,0.18) 60%, rgba(56,230,224,0.45));
  animation: ark-scan 5.5s cubic-bezier(0.4,0,0.6,1) infinite;
}
/* ── 暗角 + 内描边辉光 ─────────────────────────────────────────────────── */
.vignette {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  box-shadow: inset 0 0 240rpx 20rpx rgba(0,0,0,0.7), inset 0 0 0 2rpx rgba(56,230,224,0.10);
}

/* ── HUD 角标 ──────────────────────────────────────────────────────────── */
.hud {
  position: absolute; z-index: 2; pointer-events: none;
  font-family: 'Share Tech Mono', 'Menlo', 'Monaco', monospace;
  font-size: 18rpx; letter-spacing: 2rpx; line-height: 1.5;
  color: rgba(56,230,224,0.55); white-space: pre-line;
}
.hud-tl { left: 32rpx; top: 16rpx; }
.hud-tr { right: 32rpx; top: 16rpx; text-align: right; }
.hud-bl { left: 32rpx; bottom: 28rpx; color: rgba(56,230,224,0.6); display: flex; align-items: center; }
.hud-br { right: 32rpx; bottom: 28rpx; }
.hud-purple { color: rgba(139,92,246,0.65); }
.hud-dot {
  width: 14rpx; height: 14rpx; margin-right: 12rpx; border-radius: 50%;
  background: #2ff4e0; box-shadow: 0 0 16rpx #2ff4e0;
  animation: ark-pulse 1.4s infinite;
}

/* ── 前景内容列 ─────────────────────────────────────────────────────────── */
.content {
  position: relative; z-index: 3; width: 100%; flex: 1 1 auto;
  padding: 0 60rpx 40rpx;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  box-sizing: border-box;
  transform: translateZ(0);
}

/* ── 标语 ──────────────────────────────────────────────────────────────── */
.tagline {
  display: flex; align-items: center;
  font-weight: 500; font-size: 24rpx; letter-spacing: 16rpx; color: rgba(174,249,242,0.7);
  padding-left: 16rpx;
}
.tag-dot { color: #2ff4e0; margin: 0 8rpx; }

/* ── 副标题 ────────────────────────────────────────────────────────────── */
.subtitle {
  margin-top: 12rpx; padding-left: 18rpx;
  font-family: 'Orbitron', 'Menlo', 'Monaco', monospace;
  font-weight: 500; font-size: 26rpx; letter-spacing: 18rpx; color: rgba(120,160,210,0.85);
}

/* ── 表单卡 ────────────────────────────────────────────────────────────── */
.card {
  position: relative; width: 100%; margin-top: 28rpx;
  padding: 44rpx 44rpx 40rpx; border-radius: 28rpx;
  background: linear-gradient(180deg, rgba(14,22,42,0.72), rgba(8,14,28,0.78));
  border: 1rpx solid rgba(56,230,224,0.18);
  box-shadow: inset 0 0 60rpx rgba(20,40,80,0.4), 0 28rpx 80rpx -32rpx rgba(0,0,0,0.7);
}
/* 卡片四角括号 */
.cb { position: absolute; width: 52rpx; height: 52rpx; }
.cb-tl { left: -1rpx; top: -1rpx; border-left: 4rpx solid #2ff4e0; border-top: 4rpx solid #2ff4e0; border-radius: 8rpx 0 0 0; }
.cb-tr { right: -1rpx; top: -1rpx; border-right: 4rpx solid #2ff4e0; border-top: 4rpx solid #2ff4e0; border-radius: 0 8rpx 0 0; }
.cb-bl { left: -1rpx; bottom: -1rpx; border-left: 4rpx solid #2ff4e0; border-bottom: 4rpx solid #2ff4e0; border-radius: 0 0 0 8rpx; }
.cb-br { right: -1rpx; bottom: -1rpx; border-right: 4rpx solid #2ff4e0; border-bottom: 4rpx solid #2ff4e0; border-radius: 0 0 8rpx 0; }

/* ── 字段标签：> 前缀 + 大字距 ───────────────────────────────────────────── */
.field-label {
  display: flex; align-items: center;
  font-family: 'Rajdhani', 'Menlo', 'Monaco', monospace;
  font-weight: 700; font-size: 26rpx; letter-spacing: 6rpx; color: #8fd9ff; text-transform: uppercase;
}
.field-label-next { margin-top: 30rpx; }
.gt { color: #2ff4e0; margin-right: 12rpx; }

/* ── 输入框 ────────────────────────────────────────────────────────────── */
.field {
  position: relative; margin-top: 16rpx;
  border-radius: 20rpx;
  background: rgba(4,10,22,0.7);
  border: 1rpx solid rgba(56,230,224,0.28);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.field.focused {
  border-color: #2ff4e0;
  box-shadow: 0 0 0 1rpx rgba(47,244,224,0.6), 0 0 36rpx rgba(47,244,224,0.35);
}
.field-input {
  width: 100%; height: 100rpx; padding: 0 32rpx; box-sizing: border-box;
  color: #eaf6ff; font-size: 30rpx; background: transparent;
}
.field-input-pwd { padding: 0 88rpx 0 32rpx; }
.field-ph { color: rgba(143,217,255,0.4); }

/* 眼睛切换 */
.eye {
  position: absolute; right: 12rpx; top: 50%; transform: translateY(-50%);
  width: 68rpx; height: 68rpx;
  background-repeat: no-repeat; background-position: center; background-size: 40rpx 40rpx;
}
.eye-on { background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIj48cGF0aCBkPSJNMiAxMnM0LTcgMTAtNyAxMCA3IDEwIDctNCA3LTEwIDctMTAtNy0xMC03WiIgc3Ryb2tlPSIjMmZmNGUwIiBzdHJva2Utd2lkdGg9IjEuNiIvPjxjaXJjbGUgY3g9IjEyIiBjeT0iMTIiIHI9IjMiIHN0cm9rZT0iIzJmZjRlMCIgc3Ryb2tlLXdpZHRoPSIxLjYiLz48L3N2Zz4K"); }
.eye-off { background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIj48cGF0aCBkPSJNMiAxMnM0LTcgMTAtNyAxMCA3IDEwIDctNCA3LTEwIDctMTAtNy0xMC03WiIgc3Ryb2tlPSIjOGZiM2Q5IiBzdHJva2Utd2lkdGg9IjEuNiIvPjxjaXJjbGUgY3g9IjEyIiBjeT0iMTIiIHI9IjMiIHN0cm9rZT0iIzhmYjNkOSIgc3Ryb2tlLXdpZHRoPSIxLjYiLz48cGF0aCBkPSJNMyAzbDE4IDE4IiBzdHJva2U9IiM4ZmMzZmYiIHN0cm9rZS13aWR0aD0iMS42IiBzdHJva2UtbGluZWNhcD0icm91bmQiLz48L3N2Zz4K"); }

/* ── 注册按钮 ──────────────────────────────────────────────────────────── */
.register-btn {
  position: relative; overflow: hidden;
  width: 100%; height: 112rpx; margin-top: 40rpx; padding: 0;
  border: none; border-radius: 60rpx;
  background: linear-gradient(95deg, #22e6da 0%, #3a8bff 48%, #8b5cf6 100%);
  box-shadow: 0 0 52rpx rgba(47,244,224,0.45), 0 0 88rpx rgba(139,92,246,0.3);
  display: flex; align-items: center; justify-content: center;
}
.register-btn::after { border: none; }
.register-btn[disabled] { opacity: 1; }
.btn-txt {
  position: relative; z-index: 2;
  font-weight: 700; font-size: 36rpx; letter-spacing: 16rpx; color: #04121f;
}
.sheen {
  position: absolute; top: 0; left: 0; width: 40%; height: 100%; z-index: 1;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.55), transparent);
  animation: ark-sweep 3.4s ease-in-out infinite;
}
.btn-loading { position: relative; z-index: 2; display: flex; align-items: center; }
.btn-loading-txt { font-weight: 700; font-size: 32rpx; letter-spacing: 4rpx; color: #04121f; margin-left: 16rpx; }
.spinner {
  width: 32rpx; height: 32rpx; border-radius: 50%;
  border: 4rpx solid rgba(4,18,31,0.3); border-top-color: #04121f;
  animation: ark-spin 0.7s linear infinite;
}

/* ── 返回登录链接 ────────────────────────────────────────────────────────── */
.back-link {
  text-align: center; margin-top: 28rpx;
  font-size: 28rpx; letter-spacing: 2rpx; color: rgba(143,217,255,0.7);
}
.back-link-highlight {
  color: #2ff4e0; font-weight: 700; text-shadow: 0 0 20rpx rgba(47,244,224,0.7);
}

/* ====== keyframes（与登录页完全一致）====== */
@keyframes ark-grid { 0% { background-position: 0 0; } 100% { background-position: 0 80rpx; } }
@keyframes ark-scan { 0% { transform: translateY(-10%); opacity: 0; } 8% { opacity: 0.9; } 92% { opacity: 0.9; } 100% { transform: translateY(1520rpx); opacity: 0; } }
@keyframes ark-sweep { 0% { transform: translateX(-130%) skewX(-20deg); } 55%,100% { transform: translateX(260%) skewX(-20deg); } }
@keyframes ark-pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.35; transform: scale(0.8); } }
@keyframes ark-float { 0%,100% { transform: translate(0,0); } 50% { transform: translate(28rpx,-36rpx); } }
@keyframes ark-spin { to { transform: rotate(360deg); } }
</style>
