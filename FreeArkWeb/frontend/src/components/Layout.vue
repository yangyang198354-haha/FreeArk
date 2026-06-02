<template>
  <div class="app-shell" :class="{ 'sidebar-collapsed': isCollapsed }">
    <!-- 全局网格纹理背景（fixed 伪元素等效，用 div 实现以兼容 Vue scoped）-->
    <div class="app-grid-overlay" aria-hidden="true"></div>

    <!-- Brand / Logo 角（左上）-->
    <div class="brand-box">
      <button class="sidebar-toggle-btn" @click="toggleSidebar" :title="isCollapsed ? '展开导航栏' : '折叠导航栏'">
        <el-icon :size="18"><Fold v-if="!isCollapsed" /><Expand v-else /></el-icon>
      </button>
      <span class="brand-name">自由方舟能耗采集平台</span>
    </div>

    <!-- Topbar（右上）-->
    <header class="topbar">
      <div class="topbar-left">
        <span class="topbar-pill">
          <span class="online-dot"></span>
          实时采集 · 60s
        </span>
      </div>
      <div class="topbar-right">
        <el-dropdown @command="handleDropdownCommand">
          <div class="user-pill">
            <span class="user-avatar">{{ avatarChar }}</span>
            <span class="user-name">{{ username || '管理员' }}</span>
            <el-icon class="user-chevron"><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="editProfile">编辑个人资料</el-dropdown-item>
              <el-dropdown-item command="changePassword">修改登录密码</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <!-- Sidebar（左下）-->
    <aside class="sidebar" :class="{ 'is-collapsed': isCollapsed }">
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
          <el-menu-item index="/device-management/faults">故障管理</el-menu-item>
          <el-menu-item index="/device-management/condensation-warnings">结露预警</el-menu-item>
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

        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <template #title><span>和方舟龙虾聊天</span></template>
        </el-menu-item>

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

    <!-- Main content area（右下）-->
    <main class="main-content">
      <div class="page-container">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  User, ArrowDown, HomeFilled, Document, Setting,
  House, List, Fold, Expand, ChatDotRound
} from '@element-plus/icons-vue'
import api from '@/utils/api.js'

const SIDEBAR_STORAGE_KEY = 'freeark_sidebar_collapsed'

export default {
  name: 'Layout',
  components: {
    User, ArrowDown, HomeFilled, Document, Setting,
    House, List, Fold, Expand, ChatDotRound,
  },
  setup() {
    const router = useRouter()
    const username = ref('')
    const userRole = ref('user')
    const loading = ref(false)

    const isCollapsed = ref(
      localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true'
    )

    const avatarChar = computed(() => {
      const name = username.value
      if (name && name.length > 0) {
        return name.charAt(name.length - 1)
      }
      return '管'
    })

    const toggleSidebar = () => {
      isCollapsed.value = !isCollapsed.value
      localStorage.setItem(SIDEBAR_STORAGE_KEY, String(isCollapsed.value))
    }

    const activeMenu = computed(() => {
      return router.currentRoute.value.path
    })

    const formatFullName = (firstName, lastName) => {
      if (firstName && lastName) return `${lastName}${firstName}`
      if (firstName) return firstName
      if (lastName) return lastName
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

    const handleDropdownCommand = (command) => {
      if (command === 'editProfile') {
        const userInfo = JSON.parse(localStorage.getItem('userInfo') || '{}')
        const userId = userInfo.id
        if (userId) {
          router.push(`/edit-user/${userId}`)
        } else {
          console.error('无法获取当前用户ID')
        }
      } else if (command === 'changePassword') {
        router.push('/change-password')
      } else if (command === 'logout') {
        handleLogout()
      }
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
      avatarChar,
      toggleSidebar,
      handleDropdownCommand,
      handleLogout,
    }
  }
}
</script>

<style scoped>
/* ===========================================================================
   App Shell — CSS Grid (4-area)
   brand | topbar
   side  | main
   =========================================================================== */
.app-shell {
  position: relative;
  min-height: 100vh;
  display: grid;
  grid-template-columns: var(--sidebar-w, 244px) 1fr;
  grid-template-rows: var(--topbar-h, 60px) 1fr;
  grid-template-areas:
    "brand top"
    "side  main";
  background:
    radial-gradient(1100px 700px at 80% -5%, rgba(56,189,248,0.07), transparent 60%),
    radial-gradient(900px 600px at 0% 100%, rgba(59,130,246,0.06), transparent 60%),
    linear-gradient(180deg, #050a14 0%, #060d1c 100%);
  color: var(--ink-0);
  transition: grid-template-columns 300ms cubic-bezier(0.4, 0, 0.2, 1);
}

/* 折叠态：grid 列宽变窄 */
.app-shell.sidebar-collapsed {
  grid-template-columns: var(--sidebar-width-collapsed, 64px) 1fr;
}

/* 全局网格纹理叠加层 */
.app-grid-overlay {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background-image:
    linear-gradient(rgba(120,160,220,0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(120,160,220,0.035) 1px, transparent 1px);
  background-size: 54px 54px;
  -webkit-mask-image: radial-gradient(1200px 800px at 70% 30%, #000 0%, transparent 80%);
  mask-image: radial-gradient(1200px 800px at 70% 30%, #000 0%, transparent 80%);
}

/* ===========================================================================
   Brand Box（左上角）
   =========================================================================== */
.brand-box {
  grid-area: brand;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border-right: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  background: rgba(7,14,28,0.6);
  position: relative;
  z-index: 10;
  flex-shrink: 0;
}

.sidebar-toggle-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--ink-2);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  flex-shrink: 0;
  transition: background-color 150ms ease-in-out, color 150ms ease-in-out;
}

.sidebar-toggle-btn:hover {
  background-color: rgba(120,160,220,0.1);
  color: var(--ink-0);
}

.brand-name {
  font-size: 14.5px;
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.03em;
  color: var(--ink-0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 折叠时隐藏文字 */
.app-shell.sidebar-collapsed .brand-name {
  display: none;
}

/* ===========================================================================
   Topbar（右上）
   =========================================================================== */
.topbar {
  grid-area: top;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 26px;
  border-bottom: 1px solid var(--line);
  background: rgba(7,14,28,0.45);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  position: relative;
  z-index: 10;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.topbar-pill {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  color: var(--ink-2);
  font-family: var(--font-family-mono);
  letter-spacing: 0.06em;
}

.online-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ok);
  box-shadow: 0 0 8px var(--ok);
  flex-shrink: 0;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--panel);
  cursor: pointer;
  transition: border-color 150ms ease-in-out, background-color 150ms ease-in-out;
  user-select: none;
}

.user-pill:hover {
  border-color: var(--line-2);
  background: var(--panel-2);
}

.user-avatar {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--acc), var(--acc-2));
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: var(--font-weight-semibold);
  color: #06182a;
  flex-shrink: 0;
}

.user-name {
  font-size: 13px;
  color: var(--ink-1);
}

.user-chevron {
  color: var(--ink-2);
  font-size: 12px;
}

/* ===========================================================================
   Sidebar（左下）
   =========================================================================== */
.sidebar {
  grid-area: side;
  border-right: 1px solid var(--line);
  background: rgba(7,14,28,0.55);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  padding: 14px 10px;
  overflow-y: auto;
  overflow-x: hidden;
  position: relative;
  z-index: 5;
  transition: width 300ms cubic-bezier(0.4, 0, 0.2, 1);
}

/* el-menu 基础覆盖 */
.sidebar-menu {
  border-right: none !important;
  background-color: transparent !important;
  width: 100%;
}

/* 菜单项 */
.sidebar-menu :deep(.el-menu-item),
.sidebar-menu :deep(.el-sub-menu__title) {
  height: 44px;
  line-height: 44px;
  color: var(--ink-2) !important;
  background-color: transparent !important;
  border-radius: 10px;
  margin-bottom: 2px;
  position: relative;
  font-size: var(--font-size-nav);
  transition: color 150ms ease-in-out, background-color 150ms ease-in-out;
}

.sidebar-menu :deep(.el-menu-item .el-icon),
.sidebar-menu :deep(.el-sub-menu__title .el-icon) {
  color: var(--ink-3);
  transition: color 150ms ease-in-out;
}

/* hover 态 */
.sidebar-menu :deep(.el-menu-item:hover),
.sidebar-menu :deep(.el-sub-menu__title:hover) {
  color: var(--ink-0) !important;
  background-color: rgba(120,160,220,0.06) !important;
}

.sidebar-menu :deep(.el-menu-item:hover .el-icon),
.sidebar-menu :deep(.el-sub-menu__title:hover .el-icon) {
  color: var(--ink-1) !important;
}

/* active 态 — 渐变背景 + 左竖条 */
.sidebar-menu :deep(.el-menu-item.is-active) {
  color: #ffffff !important;
  background: linear-gradient(90deg, rgba(59,130,246,0.22), rgba(59,130,246,0.05)) !important;
}

.sidebar-menu :deep(.el-menu-item.is-active .el-icon) {
  color: var(--acc-2) !important;
}

/* active 左竖条 */
.sidebar-menu :deep(.el-menu-item.is-active)::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: linear-gradient(180deg, var(--acc), var(--acc-2));
  box-shadow: 0 0 12px var(--acc);
}

/* 子菜单列表区域 */
.sidebar-menu :deep(.el-sub-menu__list),
.sidebar-menu :deep(.el-menu--inline) {
  background-color: transparent !important;
  padding: 0 0 4px 0;
}

.sidebar-menu :deep(.el-menu--inline .el-menu-item) {
  padding-left: 44px !important;
  height: 38px;
  line-height: 38px;
  font-size: 13px;
  color: var(--ink-2) !important;
  background: transparent !important;
  border-radius: 8px;
  margin-bottom: 1px;
  position: relative;
}

/* sub-item active 态 */
.sidebar-menu :deep(.el-menu--inline .el-menu-item.is-active) {
  color: var(--acc-2) !important;
  background: rgba(59,130,246,0.1) !important;
}

/* sub-item active 小圆点 */
.sidebar-menu :deep(.el-menu--inline .el-menu-item.is-active)::after {
  content: "";
  position: absolute;
  left: 26px;
  top: 50%;
  transform: translateY(-50%);
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--acc-2);
  box-shadow: 0 0 8px var(--acc-2);
}

/* sub-item hover */
.sidebar-menu :deep(.el-menu--inline .el-menu-item:hover) {
  color: var(--ink-0) !important;
  background: rgba(120,160,220,0.05) !important;
}

/* 折叠时弹出菜单 */
:deep(.el-menu--popup) {
  background-color: rgba(10,20,36,0.97) !important;
  border: 1px solid var(--line-2) !important;
  border-radius: var(--radius-base) !important;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5) !important;
  padding: 4px !important;
}

:deep(.el-menu--popup .el-menu-item) {
  color: var(--ink-2) !important;
  background: transparent !important;
  border-radius: var(--radius-sm) !important;
  font-size: var(--font-size-nav);
}

:deep(.el-menu--popup .el-menu-item:hover) {
  background-color: rgba(120,160,220,0.06) !important;
  color: var(--ink-0) !important;
}

:deep(.el-menu--popup .el-menu-item.is-active) {
  color: #ffffff !important;
  background: linear-gradient(90deg, rgba(59,130,246,0.22), rgba(59,130,246,0.05)) !important;
}

/* 折叠时图标居中 */
.sidebar.is-collapsed :deep(.el-menu-item .el-icon),
.sidebar.is-collapsed :deep(.el-sub-menu__title .el-icon) {
  font-size: 20px;
  margin-right: 0;
}

/* ===========================================================================
   Main Content Area（右下）
   =========================================================================== */
.main-content {
  grid-area: main;
  overflow-y: auto;
  position: relative;
  z-index: 1;
  height: calc(100vh - var(--topbar-h, 60px));
}

.page-container {
  padding: 28px 32px 48px;
  max-width: var(--content-max-width, 1680px);
  margin: 0 auto;
  min-height: 100%;
}

/* ===========================================================================
   路由切换动效
   =========================================================================== */
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

/* ===========================================================================
   响应式 — <1340px 宽屏收缩
   =========================================================================== */
@media (max-width: 1339px) {
  .app-shell:not(.sidebar-collapsed) {
    grid-template-columns: var(--sidebar-width-collapsed, 64px) 1fr;
  }

  .app-shell:not(.sidebar-collapsed) .brand-name {
    display: none;
  }

  .page-container {
    padding: 20px 16px 40px;
  }
}

@media (max-width: 720px) {
  .app-shell {
    grid-template-columns: 0 1fr;
  }

  .sidebar {
    display: none;
  }

  .brand-box {
    border-right: none;
  }

  .page-container {
    padding: 16px 12px 32px;
  }
}
</style>
