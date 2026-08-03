<!--
  @module MOD-PAGE-PRIVACY
  @description 隐私保护指引页。赛博朋克 HUD 视觉风格，与个人中心一致。
    正文与微信公众平台已填报的《智能方舟座舱小程序隐私保护指引》逐条对齐，
    改动此页时必须同步修改平台填报内容，两处不一致会导致隐私合规审核驳回。
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
      <text class="header-title">隐私保护指引</text>
      <view class="header-spacer" />
    </view>

    <scroll-view scroll-y class="body" :style="scrollStyle">
      <view class="card">
        <view class="corner tl" /><view class="corner tr" />
        <view class="corner bl" /><view class="corner br" />

        <view class="section">
          <text class="section-text">本指引是智能方舟座舱小程序开发者（以下简称"开发者"）为处理你的个人信息而制定。</text>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">一、开发者处理的信息</text>
          <text class="section-text">根据法律规定，开发者仅处理实现小程序功能所必要的信息。</text>
          <view class="bullet-list">
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">开发者将在获取你的明示同意后，收集你的微信昵称、头像，用途是用于用户在个人资料页选择头像、填写昵称，完成账号个性化设置。</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">开发者将在获取你的明示同意后，访问你的麦克风，用途是用于副官页面语音输入转文字，方便你快速提问。</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">开发者将在获取你的明示同意后，访问你的摄像头，用途是用于扫描方舟座舱二维码进行座舱绑定。</text></view>
          </view>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">二、第三方插件信息 / SDK 信息</text>
          <text class="section-text">为实现特定功能，开发者可能会接入由第三方提供的插件 / SDK。第三方插件 / SDK 的个人信息处理规则，请以其公示的官方说明为准。智能方舟座舱小程序当前未接入第三方插件 / SDK。</text>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">三、未成年人保护</text>
          <text class="section-text">根据相关法律法规的规定，若你是 14 周岁以下的未成年人，你需要和你的监护人共同仔细阅读本指引，并在征得监护人明示同意后继续使用小程序服务。开发者将根据相关法律法规的规定及本指引内容，处理经监护人同意而收集的未成年人用户信息，并通过本指引"你的权益"部分披露的内容保障未成年人在个人信息处理活动中的各项权利。</text>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">四、你的权益</text>
          <view class="bullet-list">
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">关于访问你的麦克风、摄像头，你可以通过以下路径：小程序主页右上角"…"—"设置"—点击特定信息—点击"不允许"，撤回对开发者的授权。</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">关于你的个人信息，你可以通过本指引载明的联系方式与开发者联系，行使查阅、复制、更正、删除等法定权利。</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">若你在小程序中注册了账号，你可以通过本指引载明的联系方式与开发者联系，申请注销你在小程序中使用的账号。在受理你的申请后，开发者承诺在十五个工作日内完成核查和处理，并按照法律法规要求处理你的相关信息。</text></view>
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">邮箱：55086934@qq.com</text></view>
          </view>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">五、开发者对信息的存储</text>
          <text class="section-text">开发者承诺，除法律法规另有规定外，开发者对你的信息的保存期限应当为实现处理目的所必要的最短时间。</text>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">六、信息的使用规则</text>
          <text class="section-text">开发者将会在本指引所明示的用途内使用收集的信息。</text>
          <text class="section-text">如开发者使用你的信息超出本指引目的或合理范围，开发者必须在变更使用目的或范围前，再次以弹窗提示、页面提示方式告知并征得你的明示同意。</text>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">七、信息对外提供</text>
          <text class="section-text">开发者承诺，不会主动共享或转让你的信息至任何第三方，如存在确需共享或转让时，开发者应当直接征得或确认第三方征得你的单独同意。</text>
          <text class="section-text">开发者承诺，不会对外公开披露你的信息，如必须公开披露时，开发者应当向你告知公开披露的目的、披露信息的类型及可能涉及的信息，并征得你的单独同意。</text>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">八、联系与投诉</text>
          <text class="section-text">你认为开发者未遵守上述约定，或有其他的投诉建议、或未成年人个人信息保护相关问题，可通过以下方式与开发者联系；或者向微信进行投诉。</text>
          <view class="bullet-list">
            <view class="bullet"><text class="dot">•</text><text class="bullet-text">邮箱：55086934@qq.com</text></view>
          </view>
        </view>

        <view class="divider" />

        <view class="section">
          <text class="section-title">九、更新日期</text>
          <text class="section-text">本指引更新于 2026 年 8 月 3 日，自发布之日起生效。</text>
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
