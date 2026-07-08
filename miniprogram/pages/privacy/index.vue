<!--
  @module MOD-PAGE-PRIVACY
  @description 隐私政策页。赛博朋克 HUD 视觉风格，与个人中心一致。
    声明信息收集、使用目的、用户权益，满足微信隐私合规审核要求。
-->
<template>
  <view class="privacy-page">
    <!-- 背景装饰 -->
    <view class="bg-base" />
    <view class="bg-grid" />

    <!-- 状态栏占位 -->
    <view :style="{ height: statusBarHeight + 'px' }" class="status-spacer" />

    <!-- header -->
    <view class="header">
      <text class="back-btn" @tap="goBack">‹ 返回</text>
      <text class="header-title">隐私政策</text>
      <view class="header-spacer" />
    </view>

    <scroll-view scroll-y class="body" :style="scrollStyle">
      <view class="card">
        <view class="corner tl" /><view class="corner tr" />
        <view class="corner bl" /><view class="corner br" />

        <view class="section">
          <text class="section-title">一、信息收集</text>
          <text class="section-text">FreeArk（"我们"）仅在您使用以下功能时收集必要信息：</text>
          <view class="bullet-list">
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">微信登录：获取您的微信OpenID，用于识别用户身份并关联账户与绑定房号</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">头像与昵称：您在个人中心主动设置的头像和昵称，仅用于页面展示</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">麦克风：语音输入转文字功能，方便您快速向方舟副官提问。录音文件上传至服务器进行语音识别，处理后即刻删除</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">设备绑定信息：您绑定的房号（专有部分），用于查询对应设备状态和参数</text></view>
          </view>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">二、信息使用</text>
          <text class="section-text">我们收集的信息仅用于以下目的：</text>
          <view class="bullet-list">
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">提供三恒系统（温度/湿度/新风）的实时监控与参数设置</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">提供AI副官问答服务（包括能耗分析、故障排查等）</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">关联您的房号以查询对应设备数据</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">个人中心展示您的账户信息</text></view>
          </view>
          <text class="section-text" style="margin-top: 20rpx;">如我们使用您的信息超出上述目的或合理范围，我们将在变更使用目的或范围前，再次以弹窗提示、页面提示方式告知并征得您的明示同意。</text>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">三、信息存储与保护</text>
          <view class="bullet-list">
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">您的个人信息存储在位于中国境内的服务器上</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">我们采取加密传输（AES-256）、访问控制等技术措施保护您的信息安全</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">录音文件在语音识别完成后即刻删除，不留存原始音频</text></view>
          </view>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">四、第三方共享</text>
          <text class="section-text">我们不会将您的个人信息分享、出售或出租给任何第三方，以下情形除外：</text>
          <view class="bullet-list">
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">获得您的明确同意或授权</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">法律法规要求或政府机关依法要求</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">为保护我们或用户的合法权益所必需</text></view>
          </view>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">五、您的权益</text>
          <text class="section-text">您对您的个人信息享有以下权利：</text>
          <view class="bullet-list">
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">查阅与更正：您可在"舰长休息室"页面查看和修改头像、昵称</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">删除账户：您可随时退出登录，已绑定的房号可在绑定页面解绑</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">撤回授权：您可在手机系统设置中关闭麦克风权限，撤回后将无法使用语音输入功能，但不影响其他功能正常使用</text></view>
          </view>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">六、联系我们</text>
          <text class="section-text">如您对本隐私政策有任何疑问或建议，请联系我们：</text>
          <view class="bullet-list">
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">邮箱：service@freeark.com</text></view>
          </view>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">七、更新日期</text>
          <text class="section-text">本隐私政策更新于 2026年7月9日，自发布之日起生效。</text>
        </view>
      </view>

      <!-- 底部间距 -->
      <view style="height: 60rpx;" />
    </scroll-view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'

const sysInfo = uni.getSystemInfoSync()
const statusBarHeight = ref(sysInfo.statusBarHeight || 20)
const safeBottom = ref(sysInfo.safeAreaInsets ? (sysInfo.safeAreaInsets.bottom || 0) : 0)

// WeChat scroll-view 需要显式高度才能滚动（flex:1 在原生组件上不生效）。
// header: 92rpx; status-spacer + header + safeBottom 之外的全部空间给滚动区。
const rpxRate = (sysInfo.windowWidth || 375) / 750
const headerPx = Math.round(92 * rpxRate)
const scrollStyle = computed(() => {
  const h = statusBarHeight.value + headerPx + safeBottom.value
  return `height: calc(100vh - ${h}px); padding-bottom: ${safeBottom.value}px;`
})

function goBack() {
  uni.navigateBack({ delta: 1 })
}
</script>

<style scoped>
.privacy-page {
  position: relative;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #05070f;
  overflow: hidden;
}

/* ── 背景 ─────────────────────────────────────────── */
.bg-base, .bg-grid { position: absolute; pointer-events: none; }
.bg-base {
  inset: 0;
  background:
    radial-gradient(90% 45% at 18% 0%, rgba(101,55,180,0.32), transparent 55%),
    radial-gradient(80% 40% at 100% 4%, rgba(20,180,170,0.22), transparent 55%),
    linear-gradient(180deg, #0b0a1a, #07101c 60%, #050811);
}
.bg-grid {
  inset: 0;
  background-image:
    linear-gradient(rgba(56,230,224,0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56,230,224,0.06) 1px, transparent 1px);
  background-size: 80rpx 80rpx;
  -webkit-mask-image: linear-gradient(180deg, #000, transparent 55%);
  mask-image: linear-gradient(180deg, #000, transparent 55%);
}

.status-spacer { position: relative; z-index: 5; flex: 0 0 auto; }

/* ── header ───────────────────────────────────────── */
.header {
  position: relative; z-index: 5; flex: 0 0 auto;
  height: 92rpx; display: flex; align-items: center; justify-content: space-between;
  padding: 0 30rpx;
}
.back-btn { font-size: 30rpx; color: #2ff4e0; }
.header-title {
  font-family: 'Courier New', 'SF Mono', 'Menlo', monospace;
  font-size: 34rpx; font-weight: 700; letter-spacing: 6rpx;
  color: #eaf6ff;
}
.header-spacer { width: 100rpx; }

/* ── body ─────────────────────────────────────────── */
.body { position: relative; z-index: 4; flex: 0 0 auto; padding: 20rpx 36rpx; }

/* card */
.card {
  position: relative; border-radius: 32rpx;
  border: 1px solid rgba(56,230,224,0.18);
  padding: 40rpx 36rpx;
  background: linear-gradient(180deg, rgba(14,22,42,0.75), rgba(8,14,28,0.8));
  box-shadow: inset 0 0 26px rgba(20,40,80,0.35);
}
.corner { position: absolute; width: 44rpx; height: 44rpx; }
.corner.tl { left: -1px; top: -1px; border-left: 2px solid #2ff4e0; border-top: 2px solid #2ff4e0; border-radius: 8rpx 0 0 0; }
.corner.tr { right: -1px; top: -1px; border-right: 2px solid #2ff4e0; border-top: 2px solid #2ff4e0; border-radius: 0 8rpx 0 0; }
.corner.bl { left: -1px; bottom: -1px; border-left: 2px solid #2ff4e0; border-bottom: 2px solid #2ff4e0; border-radius: 0 0 0 8rpx; }
.corner.br { right: -1px; bottom: -1px; border-right: 2px solid #2ff4e0; border-bottom: 2px solid #2ff4e0; border-radius: 0 0 8rpx 0; }

/* section */
.section { margin-bottom: 10rpx; }
.section-title {
  display: block;
  font-size: 32rpx; font-weight: 700; color: #2ff4e0;
  letter-spacing: 2rpx; margin-bottom: 20rpx;
}
.section-text {
  display: block;
  font-size: 26rpx; color: rgba(219,238,255,0.85);
  line-height: 1.8; margin-bottom: 16rpx;
}
.bullet-list { padding-left: 10rpx; }
.bullet { display: flex; margin-bottom: 12rpx; }
.dot { flex: 0 0 auto; font-size: 24rpx; color: rgba(143,217,255,0.55); margin-right: 14rpx; line-height: 1.8; }
.bullet-text { flex: 1; font-size: 25rpx; color: rgba(189,214,242,0.78); line-height: 1.7; }

/* divider */
.divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(56,230,224,0.22), transparent);
  margin: 28rpx 0;
}
</style>
