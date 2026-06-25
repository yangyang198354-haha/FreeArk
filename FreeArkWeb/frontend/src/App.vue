<template>
  <div class="app-container">
    <!-- 根据路由判断是否显示Layout组件 -->
    <!-- v1.6.0：Login 与 UserLanding（业主占位页）不套用 Layout（无侧边菜单） -->
    <template v-if="$route.name === 'Login' || $route.name === 'UserLanding'">
      <!-- 登录页 / 业主占位页直接渲染 -->
      <router-view />
    </template>
    <template v-else>
      <!-- 其他页面使用Layout -->
      <Layout />
    </template>
  </div>
</template>

<script>
import Layout from './components/Layout.vue'

export default {
  name: 'App',
  components: {
    Layout
  }
}
</script>

<style>
/* App.vue 全局样式 — 深色科技风基础 */
.app-container {
  min-height: 100vh;
  background-color: var(--bg-0, #050a14);
}
</style>
