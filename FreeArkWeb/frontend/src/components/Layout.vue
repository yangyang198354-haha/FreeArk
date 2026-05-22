<template>
  <div class="app-layout">
    <!-- 顶部导航栏 -->
    <header class="app-header">
      <div class="header-left">
        <!-- 折叠触发器（AC-UI-001-04）-->
        <button class="sidebar-toggle-btn" @click="toggleSidebar" :title="isCollapsed ? '展开导航栏' : '折叠导航栏'">
          <el-icon :size="20"><Fold v-if="!isCollapsed" /><Expand v-else /></el-icon>
        </button>
        <span class="header-logo-text">自由方舟能耗采集平台</span>
      </div>
      <div class="header-right">
        <el-dropdown>
          <span class="user-info">
            <el-icon><User /></el-icon>
            {{ username || '管理员' }}
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleEditProfile">编辑个人资料</el-dropdown-item>
              <el-dropdown-item @click="handleChangePassword">修改登录密码</el-dropdown-item>
              <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <!-- 主体内容区域 -->
    <div class="app-main">
      <!-- 左侧导航栏（AC-UI-001-04/05）-->
      <aside class="app-sidebar" :class="{ 'is-collapsed': isCollapsed }">
        <el-menu
          :default-active="activeMenu"
          class="sidebar-menu"
          router
          unique-opened
          :collapse="isCollapsed"
          :collapse-transition="false"
        >
          <el-menu-item index="/home">
            <el-icon><HomeFilled /></el-icon>
            <template #title><span>系统看板</span></template>
          </el-menu-item>

          <el-sub-menu index="device-management">
            <template #title>
              <el-icon><List /></el-icon>
              <span>设备管理</span>
            </template>
            <el-menu-item index="/device-management/device-list">设备列表</el-menu-item>
          </el-sub-menu>

          <el-menu-item index="/owner-management" v-if="userRole === 'admin'">
            <el-icon><House /></el-icon>
            <template #title><span>业主信息管理</span></template>
          </el-menu-item>

          <el-sub-menu index="usage">
            <template #title>
              <el-icon><Document /></el-icon>
              <span>能耗报表</span>
            </template>
            <el-menu-item index="/monthly-usage-report">能耗月度用量报表</el-menu-item>
            <el-menu-item index="/daily-usage-report">能耗每日用量报表</el-menu-item>
            <el-menu-item index="/usage-query">用量查询</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="services">
            <template #title>
              <el-icon><Setting /></el-icon>
              <span>服务管理</span>
            </template>
            <el-menu-item index="/services">服务列表</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="user" v-if="userRole === 'admin'">
            <template #title>
              <el-icon><User /></el-icon>
              <span>用户管理</span>
            </template>
            <el-menu-item index="/create-user">创建用户</el-menu-item>
            <el-menu-item index="/user-list">用户列表</el-menu-item>
          </el-sub-menu>
        </el-menu>
      </aside>

      <!-- 右侧内容区域 -->
      <main class="app-content">
        <div class="content-wrapper">
          <router-view v-slot="{ Component }">
            <transition name="fade-slide" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </div>
      </main>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { User, ArrowDown, HomeFilled, Document, Setting, House, List, Fold, Expand } from '@element-plus/icons-vue'
import api from '@/utils/api.js'

const SIDEBAR_STORAGE_KEY = 'freeark_sidebar_collapsed'

export default {
  name: 'Layout',
  components: {
    User,
    ArrowDown,
    HomeFilled,
    Document,
    Setting,
    House,
    List,
    Fold,
    Expand,
  },
  setup() {
    const router = useRouter()
    const username = ref('')
    const userRole = ref('user')
    const loading = ref(false)

    // AC-UI-001-05: localStorage 持久化折叠状态
    const isCollapsed = ref(
      localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true'
    )

    const toggleSidebar = () => {
      isCollapsed.value = !isCollapsed.value
      localStorage.setItem(SIDEBAR_STORAGE_KEY, String(isCollapsed.value))
    }

    const activeMenu = computed(() => {
      return router.currentRoute.value.path
    })

    const formatFullName = (firstName, lastName) => {
      if (firstName && lastName) {
        return `${lastName}${firstName}`
      } else if (firstName) {
        return firstName
      } else if (lastName) {
        return lastName
      }
      return ''
    }

    const loadUserInfo = async () => {
      loading.value = true
      try {
        const response = await api.get('/api/auth/me/')
        if (response.success) {
          const fullName = formatFullName(response.data.first_name, response.data.last_name)
          username.value = fullName || response.data.username || '用户'
          userRole.value = response.data.role || 'user'
          localStorage.setItem('userInfo', JSON.stringify(response.data))
        }
      } catch (error) {
        console.error('加载用户信息失败:', error)
        const isAuthError = error.message && (
          error.message.includes('401') ||
          error.message.includes('未登录') ||
          error.message.includes('认证失败')
        )
        if (isAuthError) {
          handleLogout()
          return
        }
        const savedUserInfo = localStorage.getItem('userInfo')
        if (savedUserInfo) {
          const userInfo = JSON.parse(savedUserInfo)
          const fullName = formatFullName(userInfo.first_name, userInfo.last_name)
          username.value = fullName || userInfo.username || '用户'
          userRole.value = userInfo.role || 'user'
        } else {
          handleLogout()
        }
      } finally {
        loading.value = false
      }
    }

    const handleEditProfile = () => {
      const userInfo = JSON.parse(localStorage.getItem('userInfo') || '{}')
      const userId = userInfo.id
      if (userId) {
        router.push(`/edit-user/${userId}`)
      } else {
        console.error('无法获取当前用户ID')
      }
    }

    const handleChangePassword = () => {
      router.push('/change-password')
    }

    const handleLogout = async () => {
      await api.logout()
      localStorage.removeItem('userToken')
      localStorage.removeItem('isAuthenticated')
      localStorage.removeItem('userInfo')
      document.cookie = 'auth_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 UTC;'
      document.cookie = 'csrftoken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 UTC;'
      router.push('/login')
    }

    onMounted(() => {
      loadUserInfo()
    })

    return {
      username,
      userRole,
      isCollapsed,
      activeMenu,
      toggleSidebar,
      handleEditProfile,
      handleChangePassword,
      handleLogout,
    }
  }
}
</script>

<style scoped>
/* ---- 整体布局 ---- */
.app-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background-color: var(--color-bg-page);
}

/* ---- 顶部导航栏（§7.3）---- */
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: var(--header-height);
  padding: 0 var(--space-5);
  background-color: var(--color-header-bg);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  z-index: 100;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

/* 折叠按钮 */
.sidebar-toggle-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-header-text);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-base);
  transition: background-color 150ms ease-in-out;
  flex-shrink: 0;
}

.sidebar-toggle-btn:hover {
  background-color: rgba(255, 255, 255, 0.12);
}

.header-logo-text {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-header-text);
  white-space: nowrap;
}

.header-right .user-info {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  cursor: pointer;
  color: var(--color-header-text);
  font-size: var(--font-size-base);
  transition: opacity 150ms ease-in-out;
}

.header-right .user-info:hover {
  opacity: 0.85;
}

/* ---- 主体区域 ---- */
.app-main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ---- 左侧导航栏（§7.4）---- */
.app-sidebar {
  width: var(--sidebar-width-expanded);
  background-color: var(--color-bg-sidebar);
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.12);
  overflow-y: auto;
  overflow-x: hidden;
  flex-shrink: 0;
  /* AC-UI-001-04: 300ms 布局过渡 */
  transition: width 300ms cubic-bezier(0.4, 0, 0.2, 1);
}

.app-sidebar.is-collapsed {
  width: var(--sidebar-width-collapsed);
}

/* 菜单容器 — 高度与侧边栏等高 */
.sidebar-menu {
  border-right: none;
  height: 100%;
  background-color: var(--color-bg-sidebar) !important;
}

/* Element Plus el-menu 背景色覆盖 */
.sidebar-menu :deep(.el-menu) {
  background-color: var(--color-bg-sidebar) !important;
}

/* 菜单项样式（§7.4）*/
.sidebar-menu :deep(.el-menu-item),
.sidebar-menu :deep(.el-sub-menu__title) {
  color: #94A3B8;
  background-color: transparent;
  transition: background-color 200ms ease-out, color 200ms ease-out;
  height: 50px;
  line-height: 50px;
}

.sidebar-menu :deep(.el-menu-item:hover),
.sidebar-menu :deep(.el-sub-menu__title:hover) {
  color: var(--color-text-inverse) !important;
  background-color: var(--color-bg-sidebar-hover) !important;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  color: #FFFFFF !important;
  background-color: var(--color-bg-sidebar-active) !important;
}

/* 子菜单背景 */
.sidebar-menu :deep(.el-sub-menu__list),
.sidebar-menu :deep(.el-menu--inline) {
  background-color: rgba(0, 0, 0, 0.2) !important;
}

.sidebar-menu :deep(.el-sub-menu__list .el-menu-item) {
  padding-left: 48px !important;
}

/* 折叠时图标大小（§7.4）*/
.app-sidebar.is-collapsed :deep(.el-menu-item .el-icon),
.app-sidebar.is-collapsed :deep(.el-sub-menu__title .el-icon) {
  font-size: 20px;
  margin-right: 0;
}

/* 折叠时弹出菜单样式覆盖 */
:deep(.el-menu--popup) {
  background-color: var(--color-bg-sidebar) !important;
}

:deep(.el-menu--popup .el-menu-item) {
  color: #94A3B8;
}

:deep(.el-menu--popup .el-menu-item:hover) {
  background-color: var(--color-bg-sidebar-hover) !important;
  color: var(--color-text-inverse) !important;
}

:deep(.el-menu--popup .el-menu-item.is-active) {
  background-color: var(--color-bg-sidebar-active) !important;
  color: #FFFFFF !important;
}

/* ---- 右侧内容区域（§7.5）---- */
.app-content {
  flex: 1;
  padding: var(--space-5);
  overflow-y: auto;
  background-color: var(--color-bg-page);
  min-width: 0;
}

.content-wrapper {
  background-color: var(--color-bg-card);
  border-radius: var(--radius-base);
  padding: var(--space-5);
  box-shadow: var(--shadow-sm);
  max-width: var(--content-max-width);
  margin: 0 auto;
  width: 100%;
}

/* ---- 路由切换动效（§5.3 fade-slide）---- */
.fade-slide-enter-active {
  transition: opacity 400ms ease-out, transform 400ms ease-out;
}

.fade-slide-leave-active {
  transition: opacity 200ms ease-in;
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.fade-slide-leave-to {
  opacity: 0;
}
</style>
