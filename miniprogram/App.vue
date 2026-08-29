<script>
import { useAuthStore } from '@/store/auth'

export default {
  onLaunch() {
    // App launch: auth check handled per-page
    // vConsole 由 project.miniapp.json 的 enableVConsole: false 控制，无需运行时关闭

    // 启动即隐藏原生 tabBar。真正的底栏由各 tab 页内的 <ArkTabBar> 自绘。
    // iOS 原生 tabBar 渲染时机晚于 onLaunch，需多级延迟重试确保生效。
    const hide = () => uni.hideTabBar({ animation: false, fail: () => {} })
    hide()
    setTimeout(hide, 50)
    setTimeout(hide, 150)
    setTimeout(hide, 300)
    setTimeout(hide, 600)
    const authStore = useAuthStore()
    if (authStore.isLoggedIn) authStore.refreshAdjutantStatus()
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
