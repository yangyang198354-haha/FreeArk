<template>
  <div class="app-container">
    <el-container>
      <el-header>
        <div class="header-content">
          <h1>FreeArk Web</h1>
          <div class="nav-links">
            <router-link v-if="isLoggedIn" to="/">首页</router-link>
            <div class="nav-dropdown" v-if="isLoggedIn" ref="dropdown">
  <a class="nav-dropdown-toggle" @click="isDropdownOpen = !isDropdownOpen">能耗报表</a>
  <div class="nav-dropdown-menu" v-if="isDropdownOpen">
    <router-link to="/usage-query" class="nav-dropdown-item">用量查询</router-link>
  </div>
</div>
            <router-link v-if="!isLoggedIn" to="/login">登录</router-link>
            <button v-if="isLoggedIn" @click="handleLogout" class="logout-btn">
              登出
            </button>
            <span v-if="isLoggedIn" class="user-info">{{ userInfo.username || '管理员' }}</span>
          </div>
        </div>
      </el-header>
      <el-main>
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
      <el-footer>
        <p>FreeArk Web 系统 &copy; 2025</p>
      </el-footer>
    </el-container>
  </div>
</template>

<script>
export default {
  name: 'App',
  data() {
    return {
      isLoggedIn: false,
      userInfo: {},
      isDropdownOpen: false
    }
  },
  beforeDestroy() {
    document.removeEventListener('click', this.handleClickOutside)
  },
  created() {
    this.checkAuthStatus()
    document.addEventListener('click', this.handleClickOutside)
  },
  methods: {
    checkAuthStatus() {
      const token = localStorage.getItem('userToken')
      if (token) {
        this.isLoggedIn = true
        this.userInfo = JSON.parse(localStorage.getItem('userInfo') || '{}')
      }
    },
    async handleLogout() {
      try {
        // 导入 authApi 服务（假设已存在）
        const { authApi } = await import('./services/api.js')
        await authApi.logout()
      } catch (error) {
        // 即使后端登出失败，也要清除前端的token
        console.error('登出失败:', error)
      } finally {
        // 清除本地存储的认证信息
        localStorage.removeItem('userToken')
        localStorage.removeItem('userInfo')
        this.isLoggedIn = false
        this.userInfo = {}
        this.isDropdownOpen = false
        // 跳转到登录页
        this.$router.push('/login')
      }
    },
    handleClickOutside(e) {
      if (this.isDropdownOpen && this.$refs.dropdown && !this.$refs.dropdown.contains(e.target)) {
        this.isDropdownOpen = false
      }
    }
  }
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 100%;
}

.header-content h1 {
  color: #fff;
  margin: 0;
}

.nav-links {
  display: flex;
  gap: 20px;
}

.nav-links a {
  color: #fff;
  text-decoration: none;
  font-size: 16px;
  padding: 8px 16px;
  border-radius: 4px;
  transition: background-color 0.3s;
}

.nav-links a:hover {
  background-color: rgba(255, 255, 255, 0.2);
}

.el-header {
  background-color: #409eff;
  color: white;
  padding: 0 20px;
}

.el-footer {
  background-color: #f5f7fa;
  padding: 20px;
  text-align: center;
  border-top: 1px solid #ebeef5;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Nav dropdown styles */
.nav-dropdown {
  position: relative;
  display: inline-block;
}

.nav-dropdown-toggle {
  color: #fff;
  text-decoration: none;
  font-size: 16px;
  padding: 8px 16px;
  border-radius: 4px;
  transition: background-color 0.3s;
  cursor: pointer;
  display: block;
}

.nav-dropdown-toggle:hover {
  background-color: rgba(255, 255, 255, 0.2);
}

.nav-dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  background-color: #409eff;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  border-radius: 4px;
  margin-top: 2px;
  z-index: 1000;
  min-width: 150px;
}

.nav-dropdown-item {
  color: #fff;
  text-decoration: none;
  font-size: 16px;
  padding: 8px 16px;
  display: block;
  transition: background-color 0.3s;
}

.nav-dropdown-item:hover {
  background-color: rgba(255, 255, 255, 0.2);
}
</style>