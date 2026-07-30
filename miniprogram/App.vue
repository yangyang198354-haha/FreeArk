<script>
export default {
  onLaunch() {
    // App launch: auth check handled per-page
    // 强制关闭 vConsole（修复 APK 构建 vConsole 仍显示的问题）
    // #ifdef MP-WEIXIN
    try {
      wx.setEnableDebug({ enableDebug: false })
    } catch (e) { /* ignore */ }
    // #endif
    // #ifdef APP-PLUS
    // APP 端如果存在 vConsole 对象，直接销毁
    try {
      if (typeof window !== 'undefined' && window.vConsole) {
        window.vConsole.destroy()
      }
    } catch (e) { /* ignore */ }
    // #endif
  },
  onShow() {},
  onHide() {}
}
</script>

<style>
page {
  background-color: #05070f;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
}
/* WXSS 不支持通配选择器 *，改为枚举常用组件设置 box-sizing */
view,
text,
button,
input,
textarea,
scroll-view,
image,
navigator {
  box-sizing: border-box;
}
</style>
