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
/* App.vue 全局样式 — 深色科技风基础 */
.app-container {
  min-height: 100vh;
  background-color: var(--bg-0, #050a14);
}
</style>
