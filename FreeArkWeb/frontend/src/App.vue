<template>
  <div class="app-container">
    <!-- 根据路由判断是否显示Layout组件 -->
    <template v-if="$route.name === 'Login'">
      <!-- 登录页面直接渲染 -->
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
/* App.vue 全局样式 — 基础覆盖，Detail 由 global.css Design Token 提供 */
/* AC-UI-001-01: 使用 Design Token 替代硬编码颜色 */

/* 应用容器 */
.app-container {
  min-height: 100vh;
  background-color: var(--color-bg-page);
}
</style>