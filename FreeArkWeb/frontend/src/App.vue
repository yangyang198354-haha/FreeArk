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
/* 全局样式重置 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  color: #333;
  background-color: #f5f7fa;
}

/* 应用容器 */
.app-container {
  min-height: 100vh;
  background-color: #f5f7fa;
}
</style>