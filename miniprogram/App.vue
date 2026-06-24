<script>
export default {
  onLaunch() {
    // App launch: auth check handled per-page
  },
  onShow() {},
  onHide() {}
}
</script>

<style>
page {
  background-color: #f5f5f5;
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
