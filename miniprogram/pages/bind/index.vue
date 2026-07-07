<!--
  @module MOD-PAGE-BIND
  @description 座舱绑定页（v1.8.0 → 赛博朋克改版，REQ-BIND-001 ~ REQ-BIND-004）。
    - 扫描方舟代码（uni.scanCode 取 unique_id / screenMAC）建立神经链接
    - 手动输入座舱识别码完成链接
    - 列表：当前已链接座舱（api.getBindStatus），每项可断开链接（api.unbindOwner）
    - 合并 bind + unbind + status 于单页
    - 多对多：一个账号可链接多个座舱；重复链接后端返回 409 提示

  视觉规格（对齐登录/注册页赛博朋克主题）：
    深空底 #05070f + 霓虹网格/扫描线/CRT 纹理 + HUD 角标 + 渐变按钮。
    px → rpx 按 2× 换算，字体仅声明并回退系统栈。
-->
<template>
  <view class="bind-page">

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
        <view>v2.6.0 // NEURAL</view>
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

    <!-- ===== 前景内容列 ===== -->
    <scroll-view scroll-y class="content" :enhanced="true" :show-scrollbar="false">

      <!-- 故障标题 -->
      <view class="title-wrap">
        <text class="title title-base">绑定座舱</text>
        <text v-if="fxOn" class="title title-a">绑定座舱</text>
        <text v-if="fxOn" class="title title-b">绑定座舱</text>
      </view>
      <view class="subtitle">COCKPIT BINDING</view>

      <!-- ===== 卡片一：建立新链接 ===== -->
      <view class="card">
        <view class="cb cb-tl"></view>
        <view class="cb cb-tr"></view>
        <view class="cb cb-bl"></view>
        <view class="cb cb-br"></view>

        <view class="card-header">
          <text class="card-title">座舱链接</text>
          <text class="card-hint">扫描方舟座舱的身份铭牌，建立神经链路</text>
        </view>

        <!-- 扫描方舟代码按钮 -->
        <button
          class="scan-btn"
          :disabled="binding"
          @tap="handleScan"
        >
          <view v-if="fxOn" class="sheen"></view>
          <text class="scan-btn-txt">扫描方舟代码</text>
        </button>

        <!-- 分隔 -->
        <view class="divider">
          <view class="divider-line divider-line-l"></view>
          <text class="divider-text">或手动输入</text>
          <view class="divider-line divider-line-r"></view>
        </view>

        <!-- 手动输入行 -->
        <view class="input-row">
          <view class="field" :class="{ focused: focusField === 'mac' }">
            <input
              class="field-input"
              type="text"
              v-model="macInput"
              placeholder="输入座舱识别码"
              placeholder-class="field-ph"
              :disabled="binding"
              @focus="focusField = 'mac'"
              @blur="focusField = ''"
            />
          </view>
          <button
            class="bind-btn"
            :loading="binding"
            :disabled="binding || !macInput.trim()"
            @tap="bindByInput"
          >
            <text class="bind-btn-txt">建立链接</text>
          </button>
        </view>
      </view>

      <!-- ===== 卡片二：已链接座舱 ===== -->
      <view class="card">
        <view class="cb cb-tl"></view>
        <view class="cb cb-tr"></view>
        <view class="cb cb-bl"></view>
        <view class="cb cb-br"></view>

        <view class="card-header">
          <text class="card-title">已链接座舱</text>
        </view>

        <view v-if="loading" class="empty">
          <view class="spinner"></view>
          <text class="empty-text">扫描神经链路…</text>
        </view>
        <view v-else-if="bindings.length === 0" class="empty">
          <text class="empty-text">神经链路为空</text>
          <text class="empty-hint">扫描方舟代码以激活座舱</text>
        </view>
        <view v-else class="bind-list">
          <view class="bind-item" v-for="b in bindings" :key="b.specific_part">
            <view class="bi-info">
              <text class="bi-part">{{ b.specific_part }}</text>
              <text class="bi-loc">{{ b.location_name || '未知坐标' }}</text>
            </view>
            <button class="unbind-btn" size="mini" :disabled="binding" @tap="handleUnbind(b)">
              断开
            </button>
          </view>
        </view>
      </view>

      <!-- 底部安全间距 -->
      <view class="bottom-safe"></view>
    </scroll-view>

  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { useOwnerStore } from '@/store/owner'
import { api } from '@/utils/api'

const authStore = useAuthStore()
const ownerStore = useOwnerStore()
const bindings = computed(() => ownerStore.bindings)
const loading = ref(false)
const binding = ref(false)
const macInput = ref('')
const focusField = ref('')
const fxOn = ref(true)

const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = sysInfo.statusBarHeight || 20

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  loadStatus()
})

async function loadStatus(force = false) {
  loading.value = force || !ownerStore.bindingsLoaded
  try {
    await ownerStore.ensureBindings({ force, allowStale: !force })
  } catch (err) {
    uni.showToast({ title: '神经链路扫描失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function handleScan() {
  uni.scanCode({
    success: (res) => {
      const raw = res.result || ''
      // Debug：输出原始扫描结果（含隐藏字符），方便在开发者工具控制台对比
      console.log('[handleScan] raw:', JSON.stringify(raw))
      console.log('[handleScan] raw length:', raw.length)

      if (!raw.trim()) {
        uni.showToast({ title: '未识别到有效方舟代码', icon: 'none' })
        return
      }

      // 清洗扫描结果。
      // 二维码编码的就是 owner_info.unique_id 本身，理论上与手动输入一致；
      // 扫不出但手动能绑，说明 scanCode 返回的字符串里混入了肉眼不可见的字符。
      // 两步清理：先干掉零宽字符（JS \s 不覆盖），再清掉全部空白（含 BOM/内部换行）。
      let code = raw
        .replace(/[​-‏]/g, '')   // 零宽字符
        .replace(/[\s]+/g, '')             // 全部空白

      console.log('[handleScan] cleaned:', JSON.stringify(code))
      console.log('[handleScan] cleaned length:', code.length)

      // 部分设备生成的方舟代码带有版本前缀（如 "3:c5d29c52a237ade5"），
      // 而数据库 owner_info.unique_id 存的是冒号后面的部分，直接传会 404。
      // 匹配 \d+:… 格式，自动剥离前缀。
      const versionMatch = code.match(/^\d+:(.+)$/)
      if (versionMatch) {
        code = versionMatch[1]
        console.log('[handleScan] stripped version prefix, using:', code)
      }

      if (!code) {
        uni.showToast({ title: '未识别到有效座舱识别码', icon: 'none' })
        return
      }

      doBind(code)
    },
    fail: () => { /* 用户取消扫码，不提示 */ },
  })
}

function bindByInput() {
  const v = macInput.value.trim()
  if (!v) return
  doBind(v)
}

async function doBind(uniqueId) {
  binding.value = true
  try {
    const res = await api.bindOwner({ unique_id: uniqueId })
    uni.showToast({ title: `神经链路已建立：${res.specific_part}`, icon: 'none', duration: 2000 })
    macInput.value = ''
    ownerStore.markBindingChanged()
    await loadStatus(true)
  } catch (err) {
    const m = err.message || ''
    const msg =
      m.includes('HTTP 404') ? '未找到对应座舱，请确认方舟代码' :
      m.includes('HTTP 409') ? '该座舱已在链接中' :
      m.includes('HTTP 400') ? '座舱识别码格式无效' :
      '链接建立失败，请稍后重试'
    uni.showToast({ title: msg, icon: 'none', duration: 2500 })
  } finally {
    binding.value = false
  }
}

function handleUnbind(b) {
  uni.showModal({
    title: '断开链接',
    content: `确认断开与座舱 ${b.specific_part} 的神经链接？断开后将无法感知该座舱状态。`,
    success: async (r) => {
      if (!r.confirm) return
      binding.value = true
      try {
        await api.unbindOwner({ specific_part: b.specific_part })
        uni.showToast({ title: '链接已断开', icon: 'none' })
        ownerStore.markBindingChanged()
        await loadStatus(true)
      } catch (err) {
        uni.showToast({ title: '断开链接失败，请稍后重试', icon: 'none' })
      } finally {
        binding.value = false
      }
    },
  })
}
</script>

<style scoped>
.bind-page {
  position: relative;
  height: 100vh;
  width: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
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

/* ── CRT 扫描纹理 ─────────────────────────────────────────────────────── */
.crt-lines {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  background: repeating-linear-gradient(0deg, rgba(0,0,0,0) 0, rgba(0,0,0,0) 4rpx, rgba(0,0,0,0.16) 6rpx, rgba(0,0,0,0) 8rpx);
}
.scanline {
  position: absolute; left: 0; right: 0; top: 0; height: 240rpx; z-index: 1; pointer-events: none;
  background: linear-gradient(180deg, transparent, rgba(56,230,224,0.18) 60%, rgba(56,230,224,0.45));
  animation: ark-scan 5.5s cubic-bezier(0.4,0,0.6,1) infinite;
}
.vignette {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  box-shadow: inset 0 0 240rpx 20rpx rgba(0,0,0,0.7), inset 0 0 0 2rpx rgba(56,230,224,0.10);
}

/* ── HUD 角标 ─────────────────────────────────────────────────────────── */
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

/* ── 前景内容列 ───────────────────────────────────────────────────────── */
.content {
  position: relative; z-index: 3; flex: 1 1 auto; width: 100%;
  padding: 20rpx 48rpx 40rpx;
  box-sizing: border-box;
}

/* ── 故障标题 ─────────────────────────────────────────────────────────── */
.title-wrap { position: relative; margin-top: 16rpx; text-align: center; }
.title {
  font-weight: 900; font-size: 72rpx; letter-spacing: 8rpx; line-height: 1;
  white-space: nowrap;
}
.title-base {
  position: relative; color: #f4fbff;
  text-shadow: 0 0 36rpx rgba(56,230,224,0.85), 0 0 84rpx rgba(56,230,224,0.45);
  animation: ark-flicker 6s infinite;
}
.title-a {
  position: absolute; left: 0; top: 0; width: 100%; color: #2ff4e0;
  animation: ark-glitchA 4.5s infinite;
}
.title-b {
  position: absolute; left: 0; top: 0; width: 100%; color: #ff3da6;
  animation: ark-glitchB 4.5s infinite;
}

.subtitle {
  display: block; margin-top: 8rpx; text-align: center;
  font-family: 'Orbitron', 'Menlo', 'Monaco', monospace;
  font-weight: 500; font-size: 24rpx; letter-spacing: 14rpx; color: rgba(120,160,210,0.85);
}

/* ── 表单卡 ───────────────────────────────────────────────────────────── */
.card {
  position: relative; width: 100%; margin-top: 32rpx;
  padding: 40rpx 40rpx 36rpx; border-radius: 28rpx;
  background: linear-gradient(180deg, rgba(14,22,42,0.72), rgba(8,14,28,0.78));
  border: 1rpx solid rgba(56,230,224,0.18);
  box-shadow: inset 0 0 60rpx rgba(20,40,80,0.4), 0 28rpx 80rpx -32rpx rgba(0,0,0,0.7);
  box-sizing: border-box;
}
.cb { position: absolute; width: 52rpx; height: 52rpx; }
.cb-tl { left: -1rpx; top: -1rpx; border-left: 4rpx solid #2ff4e0; border-top: 4rpx solid #2ff4e0; border-radius: 8rpx 0 0 0; }
.cb-tr { right: -1rpx; top: -1rpx; border-right: 4rpx solid #2ff4e0; border-top: 4rpx solid #2ff4e0; border-radius: 0 8rpx 0 0; }
.cb-bl { left: -1rpx; bottom: -1rpx; border-left: 4rpx solid #2ff4e0; border-bottom: 4rpx solid #2ff4e0; border-radius: 0 0 0 8rpx; }
.cb-br { right: -1rpx; bottom: -1rpx; border-right: 4rpx solid #2ff4e0; border-bottom: 4rpx solid #2ff4e0; border-radius: 0 0 8rpx 0; }

.card-header { margin-bottom: 28rpx; }
.card-title {
  display: block;
  font-family: 'Rajdhani', 'Menlo', 'Monaco', monospace;
  font-weight: 700; font-size: 34rpx; letter-spacing: 6rpx; color: #8fd9ff;
  text-transform: uppercase;
}
.card-hint {
  display: block; margin-top: 8rpx;
  font-size: 24rpx; letter-spacing: 2rpx; color: rgba(143,217,255,0.55);
}

/* ── 扫描方舟代码按钮 ────────────────────────────────────────────────── */
.scan-btn {
  position: relative; overflow: hidden;
  width: 100%; height: 104rpx; padding: 0;
  border: none; border-radius: 60rpx;
  background: linear-gradient(95deg, #22e6da 0%, #3a8bff 48%, #8b5cf6 100%);
  box-shadow: 0 0 52rpx rgba(47,244,224,0.45), 0 0 88rpx rgba(139,92,246,0.3);
  display: flex; align-items: center; justify-content: center;
}
.scan-btn::after { border: none; }
.scan-btn[disabled] { opacity: 0.5; }
.scan-btn-txt {
  position: relative; z-index: 2;
  font-weight: 700; font-size: 34rpx; letter-spacing: 8rpx; color: #04121f;
}
.sheen {
  position: absolute; top: 0; left: 0; width: 40%; height: 100%; z-index: 1;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.55), transparent);
  animation: ark-sweep 3.4s ease-in-out infinite;
}

/* ── 分隔 ─────────────────────────────────────────────────────────────── */
.divider { display: flex; align-items: center; margin: 32rpx 0 24rpx; }
.divider-line { flex: 1; height: 1rpx; }
.divider-line-l { background: linear-gradient(90deg, transparent, rgba(56,230,224,0.4)); }
.divider-line-r { background: linear-gradient(90deg, rgba(56,230,224,0.4), transparent); }
.divider-text {
  font-family: 'Rajdhani', 'Menlo', 'Monaco', monospace;
  font-size: 24rpx; letter-spacing: 4rpx; color: rgba(143,217,255,0.55); margin: 0 20rpx;
}

/* ── 输入行 ───────────────────────────────────────────────────────────── */
.input-row { display: flex; align-items: center; gap: 16rpx; }
.field {
  position: relative; flex: 1;
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
  width: 100%; height: 88rpx; padding: 0 28rpx; box-sizing: border-box;
  color: #eaf6ff; font-size: 28rpx; background: transparent;
}
.field-ph { color: rgba(143,217,255,0.4); }

.bind-btn {
  position: relative; flex-shrink: 0;
  height: 88rpx; padding: 0 36rpx;
  border: none; border-radius: 48rpx;
  background: linear-gradient(135deg, #2ff4e0, #3a8bff);
  box-shadow: 0 0 28rpx rgba(47,244,224,0.35);
  display: flex; align-items: center; justify-content: center;
}
.bind-btn::after { border: none; }
.bind-btn[disabled] { opacity: 0.45; }
.bind-btn-txt {
  font-weight: 700; font-size: 28rpx; letter-spacing: 4rpx; color: #04121f;
}

/* ── 已链接列表 ───────────────────────────────────────────────────────── */
.empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 48rpx 0 32rpx;
}
.empty-text {
  font-size: 28rpx; letter-spacing: 2rpx; color: rgba(143,217,255,0.5);
}
.empty-hint {
  margin-top: 10rpx; font-size: 24rpx; color: rgba(143,217,255,0.35);
}
.spinner {
  width: 36rpx; height: 36rpx; margin-bottom: 20rpx; border-radius: 50%;
  border: 4rpx solid rgba(47,244,224,0.2); border-top-color: #2ff4e0;
  animation: ark-spin 0.7s linear infinite;
}

.bind-list { margin-top: 8rpx; }
.bind-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 24rpx 0; border-bottom: 1rpx solid rgba(56,230,224,0.08);
}
.bind-item:last-child { border-bottom: none; }
.bi-info { display: flex; flex-direction: column; flex: 1; overflow: hidden; }
.bi-part {
  font-size: 30rpx; font-weight: 700; letter-spacing: 2rpx; color: #eaf6ff;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.bi-loc {
  font-size: 24rpx; color: rgba(143,217,255,0.5); margin-top: 6rpx;
}
.unbind-btn {
  flex-shrink: 0; margin-left: 24rpx;
  background: transparent; color: #ff5e7a;
  border: 1rpx solid rgba(255,94,122,0.5);
  font-size: 24rpx; letter-spacing: 2rpx; border-radius: 10rpx;
  line-height: 1.8; padding: 0 20rpx;
  box-shadow: 0 0 16rpx rgba(255,94,122,0.12);
}
.unbind-btn::after { border: none; }
.unbind-btn[disabled] { opacity: 0.4; }

/* ── 底部安全区 ───────────────────────────────────────────────────────── */
.bottom-safe { height: 60rpx; }

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
</style>
