<template>
  <div class="user-landing">
    <div class="ul-card">
      <div class="ul-logo">自由方舟</div>
      <h1 class="ul-title">欢迎使用自由方舟</h1>
      <p class="ul-desc">您的专属功能正在开发中，敬请期待。</p>
      <el-button type="primary" :loading="loggingOut" class="ul-logout" @click="handleLogout">
        退出登录
      </el-button>
    </div>
  </div>
</template>

<script>
// v1.6.0 RBAC：user（普通业主/住户）登录后的占位落地页。
// 不渲染侧边菜单（App.vue 中已排除 Layout），不展示任何业务数据，仅提供退出登录入口。
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'

export default {
  name: 'UserLandingView',
  setup() {
    const router = useRouter()
    const loggingOut = ref(false)

    const handleLogout = async () => {
      loggingOut.value = true
      try {
        // api.logout() 内部已清理 userToken / CSRF / auth cookie
        await api.logout()
      } catch (e) {
        // 后端登出失败也继续本地清理（api.logout 已在 finally 中处理）
        console.warn('退出登录请求异常，已完成本地清理:', e && e.message)
      } finally {
        localStorage.removeItem('userInfo')
        ElMessage.success('已退出登录')
        loggingOut.value = false
        router.replace({ name: 'Login' })
      }
    }

    return { loggingOut, handleLogout }
  }
}
</script>

<style scoped>
.user-landing {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--bg-0, #050a14);
  padding: 24px;
}
.ul-card {
  width: 100%;
  max-width: 420px;
  text-align: center;
  padding: 48px 32px;
  border-radius: 16px;
  background: var(--bg-1, rgba(255, 255, 255, 0.03));
  border: 1px solid var(--line-0, rgba(255, 255, 255, 0.08));
}
.ul-logo {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--acc, #3b82f6);
  margin-bottom: 24px;
}
.ul-title {
  margin: 0 0 12px 0;
  font-size: 24px;
  font-weight: 600;
  color: var(--ink-0, #e6edf6);
}
.ul-desc {
  margin: 0 0 32px 0;
  font-size: 15px;
  color: var(--ink-2, #8b98a9);
  line-height: 1.6;
}
.ul-logout {
  min-width: 140px;
}
</style>
