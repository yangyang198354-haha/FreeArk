<!--
  @module MOD-PAGE-LOGIN
  @author Claude (方舟座舱 ARK Cockpit · 赛博朋克 HUD 登录改版，1:1 还原 claude design 交付稿)
  @description Login page (US-01).
    - Calls POST /api/auth/login/ via api.login()
    - Reads res.token and res.user (NOT res.user_info)
    - Saves userInfo including role via authStore.login()
    - Redirects to home on success; shows toast on 401/network error
    - If already logged in, redirects immediately to home
  视觉规格来自 design_handoff_ark_login（方舟座舱登录.dc.html）：
    深空底 + 霓虹网格/扫描线/CRT 纹理 + 故障标题 + HUD 角标 + 渐变登录按钮。
    设计稿 px → 小程序 rpx 按 2× 换算（设计画布≈375pt 宽）。
    字体：设计稿用 Orbitron/Rajdhani/Share Tech Mono/Noto Sans SC（Google Fonts）；
      小程序域名白名单不稳，故仅声明字体名并回退系统等宽栈，保留重字距以维持科技感（与参数设置页一致）。
    眼睛/微信图标 = 内联 SVG 转 base64 背景图（WXML 不支持原生 <svg> 标签）。
-->
<template>
  <view class="login-page">

    <!-- ===== 背景装饰（与个人中心/AI问答一致的赛博朋克基底）===== -->
    <view class="bg-base"></view>
    <view class="bg-grid"></view>
    <view class="bg-blob"></view>

    <!-- ===== 顶部特效层（扫描线/CRT/暗角/HUD角标，由 fxOn 控制）===== -->
    <template v-if="fxOn">
      <view class="blob blob-1"></view>
      <view class="blob blob-2"></view>
      <view class="crt-lines"></view>
      <view class="scanline"></view>
      <view class="vignette"></view>

      <!-- HUD 角标（装饰）-->
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

    <!-- 状态栏占位（custom 导航，与个人中心/AI问答一致）-->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer"></view>

    <!-- ===== 前景内容列 ===== -->
    <view class="content">

      <!-- logo 徽标 -->
      <view class="logo">
        <view class="logo-fill"></view>
        <template v-if="fxOn">
          <view class="logo-ring"></view>
          <view class="lb lb-tl"></view>
          <view class="lb lb-tr"></view>
          <view class="lb lb-bl"></view>
          <view class="lb lb-br"></view>
        </template>
        <text class="logo-text">ARK</text>
      </view>

      <!-- 标语 -->
      <view class="tagline">胖子熊<text class="tag-dot">·</text>智能</view>

      <!-- 故障标题 -->
      <view class="title-wrap">
        <text class="title title-base">方舟座舱</text>
        <text v-if="fxOn" class="title title-a">方舟座舱</text>
        <text v-if="fxOn" class="title title-b">方舟座舱</text>
      </view>
      <view class="subtitle">ARK COCKPIT</view>

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
            placeholder="请输入账号"
            placeholder-class="field-ph"
            :disabled="loading"
            @focus="focusField = 'user'"
            @blur="focusField = ''"
          />
        </view>

        <!-- 密码 -->
        <view class="field-label field-label-pwd"><text class="gt">&gt;</text>密码</view>
        <view class="field" :class="{ focused: focusField === 'pwd' }">
          <input
            class="field-input field-input-pwd"
            type="text"
            :password="!showPwd"
            v-model="password"
            placeholder="请输入密码"
            placeholder-class="field-ph"
            :disabled="loading"
            @focus="focusField = 'pwd'"
            @blur="focusField = ''"
          />
          <view class="eye" :class="showPwd ? 'eye-on' : 'eye-off'" @tap="showPwd = !showPwd"></view>
        </view>

        <!-- 登录按钮 -->
        <button
          class="login-btn"
          :disabled="loading"
          @tap="handleLogin"
        >
          <view v-if="fxOn" class="sheen"></view>
          <view v-if="loading" class="btn-loading">
            <view class="spinner"></view>
            <text class="btn-loading-txt">验证中</text>
          </view>
          <text v-else class="btn-txt">登 录</text>
        </button>

        <!-- 分隔 -->
        <view class="divider">
          <view class="divider-line divider-line-l"></view>
          <text class="divider-text">或</text>
          <view class="divider-line divider-line-r"></view>
        </view>

        <!-- v1.12.0: 记住我 checkbox（共用，默认 false） -->
        <view class="remember-row" @tap="rememberMe = !rememberMe">
          <checkbox :checked="rememberMe" class="remember-checkbox" color="#2ff4e0" />
          <text class="remember-label">记住我（7 天内免登录）</text>
        </view>

        <!-- 微信一键登录 -->
        <button
          class="wechat-btn"
          :disabled="loading || wxLoading"
          @tap="handleWechatLogin"
        >
          <view class="wechat-icon"></view>
          <text class="wechat-txt">{{ wxLoading ? '登录中…' : '微信一键登录' }}</text>
        </button>

        <!-- 注册 -->
        <view class="register">没有账号？<text class="register-link" @tap="goRegister">立即注册</text></view>
      </view>

    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { useOwnerStore } from '@/store/owner'
import { api } from '@/utils/api'

const authStore = useAuthStore()
const ownerStore = useOwnerStore()
const username = ref('')
const password = ref('')
const loading = ref(false)
const wxLoading = ref(false)
const showPwd = ref(false)
const focusField = ref('')
const fxOn = ref(true)
const rememberMe = ref(false)  // v1.12.0: 记住我 checkbox，默认 false

const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = sysInfo.statusBarHeight || 20

if (authStore.isLoggedIn) {
  uni.reLaunch({ url: '/pages/home/index' })
}

async function handleLogin() {
  if (!username.value.trim() || !password.value) {
    uni.showToast({ title: '请输入账号和密码', icon: 'none' })
    return
  }
  loading.value = true
  try {
    const res = await api.login({
      username: username.value.trim(),
      password: password.value,
      remember_me: rememberMe.value,
    })
    if (res.success && res.token) {
      // Backend returns res.user (NOT res.user_info) — contains id, username, email, role, first_name, last_name
      authStore.login(res.token, res.user)
      prefetchOwnerData(res.user)
      uni.reLaunch({ url: '/pages/home/index' })
    } else {
      throw new Error('登录失败')
    }
  } catch (err) {
    password.value = ''
    const msg =
      err.message.includes('SESSION_EXPIRED') ? '账号或密码错误' :
      err.message.includes('401') ? '账号或密码错误' :
      err.message.includes('HTTP 400') ? '账号或密码错误' :
      '登录失败，请检查网络'
    uni.showToast({ title: msg, icon: 'none', duration: 2000 })
  } finally {
    loading.value = false
  }
}

// v1.8.0：微信一键登录（REQ-AUTH-002）。uni.login 取临时 code → 后端 code2session 换 token。
function handleWechatLogin() {
  wxLoading.value = true
  uni.login({
    provider: 'weixin',
    success: async (loginRes) => {
      const code = loginRes && loginRes.code
      if (!code) {
        wxLoading.value = false
        uni.showToast({ title: '微信登录失败：未获取到 code', icon: 'none' })
        return
      }
      try {
        const res = await api.miniappWechatLogin({ code, remember_me: rememberMe.value })
        if (res && res.token) {
          authStore.login(res.token, res.user)
          prefetchOwnerData(res.user)
          // v1.12.0: 新用户引导设置头像昵称，老用户直接进首页（REQ-PROFILE-001, OQ-01=A）
          if (res.is_new) {
            uni.reLaunch({ url: '/pages/profile-setup/index?mode=initial' })
          } else {
            uni.reLaunch({ url: '/pages/home/index' })
          }
        } else {
          throw new Error('微信登录失败')
        }
      } catch (err) {
        const m = err.message || ''
        const msg =
          m.includes('HTTP 503') ? '微信服务暂不可用，请稍后重试' :
          m.includes('HTTP 400') ? '微信授权失败，请重试' :
          '微信登录失败，请检查网络'
        uni.showToast({ title: msg, icon: 'none', duration: 2500 })
      } finally {
        wxLoading.value = false
      }
    },
    fail: () => {
      wxLoading.value = false
      uni.showToast({ title: '微信登录已取消', icon: 'none' })
    },
  })
}

function prefetchOwnerData(user) {
  if (user?.role === 'user') ownerStore.bootstrapAfterLogin().catch(() => {})
}

function goRegister() {
  uni.navigateTo({ url: '/pages/register/index' })
}
</script>

<style scoped>
.login-page {
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

/* ── 背景基底：与个人中心/AI问答/参数设置页一致的赛博朋克色值 ───────── */
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

/* ── 光晕团 ─────────────────────────────────────────────────────────── */
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

/* ── CRT 扫描纹理 ───────────────────────────────────────────────────── */
.crt-lines {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  background: repeating-linear-gradient(0deg, rgba(0,0,0,0) 0, rgba(0,0,0,0) 4rpx, rgba(0,0,0,0.16) 6rpx, rgba(0,0,0,0) 8rpx);
}
/* ── 扫描线：240rpx 高青色渐变条，竖向扫过 ──────────────────────────── */
.scanline {
  position: absolute; left: 0; right: 0; top: 0; height: 240rpx; z-index: 1; pointer-events: none;
  background: linear-gradient(180deg, transparent, rgba(56,230,224,0.18) 60%, rgba(56,230,224,0.45));
  animation: ark-scan 5.5s cubic-bezier(0.4,0,0.6,1) infinite;
}
/* ── 暗角 + 内描边辉光 ──────────────────────────────────────────────── */
.vignette {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  box-shadow: inset 0 0 240rpx 20rpx rgba(0,0,0,0.7), inset 0 0 0 2rpx rgba(56,230,224,0.10);
}

/* ── HUD 角标 ───────────────────────────────────────────────────────── */
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

/* ── 前景内容列 ─────────────────────────────────────────────────────── */
.content {
  position: relative; z-index: 3; width: 100%; flex: 1 1 auto;
  padding: 20rpx 60rpx 40rpx;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  box-sizing: border-box;
  transform: translateZ(0);
}

/* ── logo 徽标：96px→192rpx ─────────────────────────────────────────── */
.logo {
  position: relative; width: 192rpx; height: 192rpx; margin-top: 8rpx;
  display: flex; align-items: center; justify-content: center;
}
.logo-fill {
  position: absolute; inset: 0; border-radius: 48rpx;
  background: linear-gradient(150deg, rgba(47,244,224,0.16), rgba(139,92,246,0.16));
  border: 1rpx solid rgba(56,230,224,0.4);
  box-shadow: 0 0 56rpx rgba(47,244,224,0.32), inset 0 0 36rpx rgba(47,244,224,0.12);
}
.logo-ring {
  position: absolute; width: 232rpx; height: 232rpx; border-radius: 50%;
  border: 1rpx dashed rgba(56,230,224,0.35);
  animation: ark-rotateRing 14s linear infinite;
}
.lb { position: absolute; width: 36rpx; height: 36rpx; }
.lb-tl { left: -12rpx; top: -12rpx; border-left: 4rpx solid #2ff4e0; border-top: 4rpx solid #2ff4e0; animation: ark-corner 2.4s infinite; }
.lb-tr { right: -12rpx; top: -12rpx; border-right: 4rpx solid #2ff4e0; border-top: 4rpx solid #2ff4e0; animation: ark-corner 2.4s infinite 0.6s; }
.lb-bl { left: -12rpx; bottom: -12rpx; border-left: 4rpx solid #2ff4e0; border-bottom: 4rpx solid #2ff4e0; animation: ark-corner 2.4s infinite 1.2s; }
.lb-br { right: -12rpx; bottom: -12rpx; border-right: 4rpx solid #2ff4e0; border-bottom: 4rpx solid #2ff4e0; animation: ark-corner 2.4s infinite 1.8s; }
.logo-text {
  position: relative;
  font-family: 'Orbitron', 'Menlo', 'Monaco', monospace;
  font-weight: 900; font-size: 52rpx; letter-spacing: 2rpx; color: #aef9f2;
  text-shadow: 0 0 28rpx rgba(47,244,224,0.9);
}

/* ── 标语 ───────────────────────────────────────────────────────────── */
.tagline {
  margin-top: 12rpx; display: flex; align-items: center;
  font-weight: 500; font-size: 24rpx; letter-spacing: 16rpx; color: rgba(174,249,242,0.7);
  padding-left: 16rpx;
}
.tag-dot { color: #2ff4e0; margin: 0 8rpx; }

/* ── 故障标题：44px→88rpx，三层叠加 ─────────────────────────────────── */
.title-wrap { position: relative; margin-top: 16rpx; }
.title {
  font-weight: 900; font-size: 88rpx; letter-spacing: 8rpx; line-height: 1;
  white-space: nowrap;
}
.title-base {
  position: relative; color: #f4fbff;
  text-shadow: 0 0 36rpx rgba(56,230,224,0.85), 0 0 84rpx rgba(56,230,224,0.45);
  animation: ark-flicker 6s infinite;
}
/* 不用 mix-blend-mode（真机 webview 隔离合成可能整页翻白）；用偏移 + 透明度闪现做 RGB 分离故障感 */
.title-a {
  position: absolute; left: 0; top: 0; color: #2ff4e0;
  animation: ark-glitchA 4.5s infinite;
}
.title-b {
  position: absolute; left: 0; top: 0; color: #ff3da6;
  animation: ark-glitchB 4.5s infinite;
}

/* ── 副标题：13px→26rpx ─────────────────────────────────────────────── */
.subtitle {
  margin-top: 8rpx; padding-left: 18rpx;
  font-family: 'Orbitron', 'Menlo', 'Monaco', monospace;
  font-weight: 500; font-size: 26rpx; letter-spacing: 18rpx; color: rgba(120,160,210,0.85);
}

/* ── 表单卡：radius 14px→28rpx，padding 22/22/20px ───────────────────── */
.card {
  position: relative; width: 100%; margin-top: 24rpx;
  padding: 44rpx 44rpx 40rpx; border-radius: 28rpx;
  background: linear-gradient(180deg, rgba(14,22,42,0.72), rgba(8,14,28,0.78));
  border: 1rpx solid rgba(56,230,224,0.18);
  box-shadow: inset 0 0 60rpx rgba(20,40,80,0.4), 0 28rpx 80rpx -32rpx rgba(0,0,0,0.7);
}
/* 卡片四角括号：26px→52rpx */
.cb { position: absolute; width: 52rpx; height: 52rpx; }
.cb-tl { left: -1rpx; top: -1rpx; border-left: 4rpx solid #2ff4e0; border-top: 4rpx solid #2ff4e0; border-radius: 8rpx 0 0 0; }
.cb-tr { right: -1rpx; top: -1rpx; border-right: 4rpx solid #2ff4e0; border-top: 4rpx solid #2ff4e0; border-radius: 0 8rpx 0 0; }
.cb-bl { left: -1rpx; bottom: -1rpx; border-left: 4rpx solid #2ff4e0; border-bottom: 4rpx solid #2ff4e0; border-radius: 0 0 0 8rpx; }
.cb-br { right: -1rpx; bottom: -1rpx; border-right: 4rpx solid #2ff4e0; border-bottom: 4rpx solid #2ff4e0; border-radius: 0 0 8rpx 0; }

/* ── 字段标签：> 前缀 + 大字距 ──────────────────────────────────────── */
.field-label {
  display: flex; align-items: center;
  font-family: 'Rajdhani', 'Menlo', 'Monaco', monospace;
  font-weight: 700; font-size: 26rpx; letter-spacing: 6rpx; color: #8fd9ff; text-transform: uppercase;
}
.field-label-pwd { margin-top: 36rpx; }
.gt { color: #2ff4e0; margin-right: 12rpx; }

/* ── 输入框：height 50px→100rpx ─────────────────────────────────────── */
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

/* 眼睛切换：base64 内联 SVG 背景 */
.eye {
  position: absolute; right: 12rpx; top: 50%; transform: translateY(-50%);
  width: 68rpx; height: 68rpx;
  background-repeat: no-repeat; background-position: center; background-size: 40rpx 40rpx;
}
.eye-on { background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIj48cGF0aCBkPSJNMiAxMnM0LTcgMTAtNyAxMCA3IDEwIDctNCA3LTEwIDctMTAtNy0xMC03WiIgc3Ryb2tlPSIjMmZmNGUwIiBzdHJva2Utd2lkdGg9IjEuNiIvPjxjaXJjbGUgY3g9IjEyIiBjeT0iMTIiIHI9IjMiIHN0cm9rZT0iIzJmZjRlMCIgc3Ryb2tlLXdpZHRoPSIxLjYiLz48L3N2Zz4K"); }
.eye-off { background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIj48cGF0aCBkPSJNMiAxMnM0LTcgMTAtNyAxMCA3IDEwIDctNCA3LTEwIDctMTAtNy0xMC03WiIgc3Ryb2tlPSIjOGZiM2Q5IiBzdHJva2Utd2lkdGg9IjEuNiIvPjxjaXJjbGUgY3g9IjEyIiBjeT0iMTIiIHI9IjMiIHN0cm9rZT0iIzhmYjNkOSIgc3Ryb2tlLXdpZHRoPSIxLjYiLz48cGF0aCBkPSJNMyAzbDE4IDE4IiBzdHJva2U9IiM4ZmMzZmYiIHN0cm9rZS13aWR0aD0iMS42IiBzdHJva2UtbGluZWNhcD0icm91bmQiLz48L3N2Zz4K"); }

/* ── 登录按钮：56px→112rpx，青→蓝→紫渐变 + 流光 ────────────────────── */
.login-btn {
  position: relative; overflow: hidden;
  width: 100%; height: 112rpx; margin-top: 40rpx; padding: 0;
  border: none; border-radius: 60rpx;
  background: linear-gradient(95deg, #22e6da 0%, #3a8bff 48%, #8b5cf6 100%);
  box-shadow: 0 0 52rpx rgba(47,244,224,0.45), 0 0 88rpx rgba(139,92,246,0.3);
  display: flex; align-items: center; justify-content: center;
}
.login-btn::after { border: none; }
.login-btn[disabled] { opacity: 1; }
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

/* ── 分隔 ───────────────────────────────────────────────────────────── */
.divider { display: flex; align-items: center; margin: 40rpx 0 8rpx; }
.divider-line { flex: 1; height: 1rpx; }
.divider-line-l { background: linear-gradient(90deg, transparent, rgba(56,230,224,0.4)); }
.divider-line-r { background: linear-gradient(90deg, rgba(56,230,224,0.4), transparent); }
.divider-text {
  font-family: 'Rajdhani', 'Menlo', 'Monaco', monospace;
  font-size: 26rpx; letter-spacing: 4rpx; color: rgba(143,217,255,0.7); margin: 0 24rpx;
}

/* ── 记住我（v1.12.0）───────────────────────────────────────────────── */
.remember-row {
  display: flex; align-items: center; justify-content: center; margin: 16rpx 0 0;
  padding: 8rpx 0;
}
.remember-checkbox { transform: scale(0.8); }
.remember-label {
  font-size: 24rpx; letter-spacing: 2rpx; color: rgba(143,217,255,0.6);
}

/* ── 微信一键登录：50px→100rpx ──────────────────────────────────────── */
.wechat-btn {
  position: relative;
  width: 100%; height: 100rpx; margin-top: 24rpx; padding: 0;
  border-radius: 56rpx; background: rgba(7,193,96,0.06);
  border: 1rpx solid rgba(52,232,158,0.6);
  box-shadow: inset 0 0 36rpx rgba(52,232,158,0.12), 0 0 36rpx rgba(52,232,158,0.2);
  display: flex; align-items: center; justify-content: center;
}
.wechat-btn::after { border: none; }
.wechat-icon {
  width: 44rpx; height: 44rpx; margin-right: 20rpx;
  background-repeat: no-repeat; background-position: center; background-size: 44rpx 44rpx;
  background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMiIgaGVpZ2h0PSIyMiIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSIjNWZmMGI2Ij48cGF0aCBkPSJNOS4yIDNDNSAzIDEuNiA1LjggMS42IDkuM2MwIDIgMS4xIDMuOCAyLjkgNWwtLjcgMi4yIDIuNi0xLjNjLjkuMiAxLjguNCAyLjguNGguNWE1LjYgNS42IDAgMCAxLS4yLTEuNWMwLTMuMiAzLjEtNS44IDYuOS01LjhoLjZDMTYuNyA1LjEgMTMuMyAzIDkuMiAzWm0tMi41IDMuM2EuOTUuOTUgMCAxIDEgMCAxLjkuOTUuOTUgMCAwIDEgMC0xLjlabTUgMGEuOTUuOTUgMCAxIDEgMCAxLjkuOTUuOTUgMCAwIDEgMC0xLjlaIi8+PHBhdGggZD0iTTIyLjQgMTQuMWMwLTIuOC0yLjgtNS4xLTYuMi01LjFzLTYuMiAyLjMtNi4yIDUuMWMwIDIuOSAyLjggNS4xIDYuMiA1LjEuNyAwIDEuNC0uMSAyLjEtLjNsMS45IDEtLjUtMS43YzEuNi0xIDIuNy0yLjUgMi43LTQuMVptLTguMi0xLjJhLjguOCAwIDEgMSAwLTEuNi44LjggMCAwIDEgMCAxLjZabTQgMGEuOC44IDAgMSAxIDAtMS42LjguOCAwIDAgMSAwIDEuNloiLz48L3N2Zz4K");
}
.wechat-txt {
  font-weight: 700; font-size: 32rpx; letter-spacing: 4rpx; color: #5ff0b6;
  text-shadow: 0 0 20rpx rgba(52,232,158,0.6);
}

/* ── 注册 ───────────────────────────────────────────────────────────── */
.register {
  text-align: center; margin-top: 28rpx;
  font-size: 28rpx; letter-spacing: 2rpx; color: rgba(143,217,255,0.7);
}
.register-link {
  color: #2ff4e0; font-weight: 700; text-shadow: 0 0 20rpx rgba(47,244,224,0.7);
}

/* ====== keyframes ====== */
@keyframes ark-grid { 0% { background-position: 0 0; } 100% { background-position: 0 80rpx; } }
@keyframes ark-scan { 0% { transform: translateY(-10%); opacity: 0; } 8% { opacity: 0.9; } 92% { opacity: 0.9; } 100% { transform: translateY(1520rpx); opacity: 0; } }
@keyframes ark-flicker { 0%,18%,22%,25%,53%,57%,100% { opacity: 1; } 20%,24%,55% { opacity: 0.72; } }
@keyframes ark-sweep { 0% { transform: translateX(-130%) skewX(-20deg); } 55%,100% { transform: translateX(260%) skewX(-20deg); } }
@keyframes ark-pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.35; transform: scale(0.8); } }
@keyframes ark-float { 0%,100% { transform: translate(0,0); } 50% { transform: translate(28rpx,-36rpx); } }
@keyframes ark-glitchA { 0%,100% { transform: translate(0,0); opacity: 0; } 47% { opacity: 0; } 48% { transform: translate(-4rpx,2rpx); opacity: 0.8; } 52% { transform: translate(4rpx,-2rpx); opacity: 0.8; } 53% { opacity: 0; } 80% { opacity: 0; } 81% { transform: translate(-6rpx,0); opacity: 0.7; } 83% { opacity: 0; } }
@keyframes ark-glitchB { 0%,100% { transform: translate(0,0); opacity: 0; } 47% { opacity: 0; } 48% { transform: translate(4rpx,-2rpx); opacity: 0.8; } 52% { transform: translate(-4rpx,2rpx); opacity: 0.8; } 53% { opacity: 0; } 80% { opacity: 0; } 81% { transform: translate(6rpx,0); opacity: 0.7; } 83% { opacity: 0; } }
@keyframes ark-spin { to { transform: rotate(360deg); } }
@keyframes ark-corner { 0%,100% { opacity: 0.55; } 50% { opacity: 1; } }
@keyframes ark-rotateRing { to { transform: rotate(-360deg); } }
</style>
