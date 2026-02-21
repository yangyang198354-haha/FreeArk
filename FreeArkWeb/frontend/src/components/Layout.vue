<template>
  <div class="app-layout">
    <!-- 顶部导航栏 -->
    <header class="app-header">
      <div class="header-left">
        <div class="logo">自由方舟能耗采集平台</div>
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
      <!-- 左侧导航栏 -->
      <aside class="app-sidebar">
        <el-menu
          :default-active="activeMenu"
          class="sidebar-menu"
          router
          unique-opened
        >
          <el-menu-item index="/home">
            <el-icon><HomeFilled /></el-icon>
            <span>系统看板</span>
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
            <el-menu-item index="/plc-status">PLC在线离线监控</el-menu-item>
          </el-sub-menu>
          
          <!-- 只有管理员才能看到用户管理菜单 -->
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
            <transition name="fade" mode="out-in">
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
// 导入 Element Plus 图标组件
import { User, ArrowDown, HomeFilled, Document, Setting } from '@element-plus/icons-vue'
import api from '@/utils/api.js'

export default {
  name: 'Layout',
  components: {
    User,
    ArrowDown,
    HomeFilled,
    Document,
    Setting
  },
  setup() {
    const router = useRouter()
    const username = ref('')
    const userRole = ref('user')
    const loading = ref(false)
    
    // 计算当前激活的菜单项
    const activeMenu = computed(() => {
      return router.currentRoute.value.path
    })
    
    // 格式化用户全名
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
    
    // 加载用户信息
    const loadUserInfo = async () => {
      loading.value = true
      try {
        const response = await api.get('/api/auth/me/')
        if (response.success) {
          // 优先显示用户姓名，其次是用户名
          const fullName = formatFullName(response.data.first_name, response.data.last_name)
          username.value = fullName || response.data.username || '用户'
          userRole.value = response.data.role || 'user'
          // 保存用户信息到localStorage
          localStorage.setItem('userInfo', JSON.stringify(response.data))
        }
      } catch (error) {
        console.error('加载用户信息失败:', error)
        // 如果加载失败，尝试从localStorage获取
        const savedUserInfo = localStorage.getItem('userInfo')
        if (savedUserInfo) {
          const userInfo = JSON.parse(savedUserInfo)
          // 优先显示用户姓名，其次是用户名
          const fullName = formatFullName(userInfo.first_name, userInfo.last_name)
          username.value = fullName || userInfo.username || '用户'
          userRole.value = userInfo.role || 'user'
        } else {
          // 清除认证状态，跳转到登录页
          handleLogout()
        }
      } finally {
        loading.value = false
      }
    }
    
    // 编辑个人资料处理
    const handleEditProfile = () => {
      // 从localStorage获取当前用户ID
      const userInfo = JSON.parse(localStorage.getItem('userInfo') || '{}')
      const userId = userInfo.id
      if (userId) {
        router.push(`/edit-user/${userId}`)
      } else {
        console.error('无法获取当前用户ID')
      }
    }
    
    // 修改密码处理
    const handleChangePassword = () => {
      router.push('/change-password')
    }
    
    // 退出登录处理
    const handleLogout = () => {
      // 清除本地存储的token和用户信息
      localStorage.removeItem('userToken')
      localStorage.removeItem('isAuthenticated')
      localStorage.removeItem('userInfo')
      // 清除cookie
      document.cookie = 'auth_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 UTC;'
      // 跳转到登录页面
      router.push('/login')
    }
    
    // 组件挂载时加载用户信息
    onMounted(() => {
      loadUserInfo()
    })
    
    return {
      username,
      userRole,
      activeMenu,
      handleEditProfile,
      handleChangePassword,
      handleLogout
    }
  }
}</script>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background-color: #f5f7fa;
}

/* 顶部导航栏 */
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 60px;
  padding: 0 20px;
  background-color: #409eff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  z-index: 100;
}

.header-left .logo {
  font-size: 18px;
  font-weight: 600;
  color: #fff;
}

.header-right .user-info {
  display: flex;
  align-items: center;
  cursor: pointer;
  color: #fff;
}

.header-right .el-icon {
  margin-right: 5px;
  color: #fff;
}

/* 主体内容区域 */
.app-main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* 左侧导航栏 */
.app-sidebar {
  width: 200px;
  background-color: #304156;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.05);
  overflow-y: auto;
}

/* 左侧菜单样式 */
.sidebar-menu {
  border-right: none;
  height: 100%;
  background-color: #304156;
}

/* 修改Element Plus菜单样式 */
.sidebar-menu :deep(.el-menu) {
  background-color: #304156;
  color: #c0c4cc;
}

.sidebar-menu :deep(.el-menu-item),
.sidebar-menu :deep(.el-sub-menu__title) {
  color: #c0c4cc;
  background-color: transparent;
}

.sidebar-menu :deep(.el-menu-item:hover),
.sidebar-menu :deep(.el-sub-menu__title:hover) {
  color: #fff;
  background-color: #409eff;
}

.sidebar-menu :deep(.el-menu-item.is-active),
.sidebar-menu :deep(.el-sub-menu__title.is-active) {
  color: #fff;
  background-color: #409eff;
}

.sidebar-menu :deep(.el-sub-menu__title .el-icon),
.sidebar-menu :deep(.el-menu-item .el-icon) {
  color: inherit;
}

.sidebar-menu :deep(.el-sub-menu__list) {
  background-color: #304156;
}

/* 右侧内容区域 */
.app-content {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  background-color: #f5f7fa;
}

.content-wrapper {
  background-color: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
}

/* 淡入淡出过渡效果 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>