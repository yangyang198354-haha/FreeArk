<template>
  <div class="page-container">
    <div class="page-header">
      <h2>用户列表</h2>
    </div>
    
    <!-- 用户列表 -->
    <div class="card">
      <div class="card-body">
        <div id="userListMessage" class="mb-3"></div>
        <div class="table-responsive">
          <table class="table table-striped">
            <thead>
              <tr>
                <th>用户名</th>
                <th>电子邮箱</th>
                <th>姓名</th>
                <th>角色</th>
                <th>部门</th>
                <th>职位</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody id="userListBody">
              <tr v-for="user in users" :key="user.id">
                <td>{{ user.username }}</td>
                <td>{{ user.email }}</td>
                <td>{{ formatFullName(user.first_name, user.last_name) }}</td>
                <td>{{ user.role }}</td>
                <td>{{ user.department }}</td>
                <td>{{ user.position }}</td>
                <td>{{ formatDateTime(user.created_at) }}</td>
                <td>
                  <button class="btn btn-sm btn-primary" @click="editUser(user.id)">编辑</button>
                  <button class="btn btn-sm btn-danger" @click="deleteUser(user.id)" style="margin-left: 5px;">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div id="userListMessageBottom" class="mt-3"></div>
      </div>
    </div>
  </div>
</template>

<script>
import { userApi } from '../services/api'

export default {
  name: 'UserListView',
  data() {
    return {
      users: [],
      loading: false,
      message: ''
    }
  },
  mounted() {
    this.loadUsers()
  },
  methods: {
    async loadUsers() {
      this.loading = true
      try {
        const response = await userApi.getUsers()
        if (response.data) {
          this.users = response.data
        }
      } catch (error) {
        console.error('加载用户列表失败:', error)
        this.showMessage('加载用户列表失败', 'error')
      } finally {
        this.loading = false
      }
    },
    
    editUser(userId) {
      // 跳转到编辑用户页面
      this.$router.push(`/edit-user/${userId}`)
    },
    
    async deleteUser(userId) {
      if (confirm('确定要删除这个用户吗？')) {
        try {
          await userApi.deleteUser(userId)
          this.showMessage('用户删除成功', 'success')
          this.loadUsers()
        } catch (error) {
          console.error('删除用户失败:', error)
          this.showMessage('删除用户失败', 'error')
        }
      }
    },
    
    showMessage(message, type) {
      const messageElement = document.getElementById('userListMessage')
      messageElement.textContent = message
      messageElement.className = `mb-3 alert alert-${type}`
      
      // 3秒后自动隐藏消息
      setTimeout(() => {
        messageElement.textContent = ''
        messageElement.className = 'mb-3'
      }, 3000)
    },
    
    // 判断字符串是否包含中文字符
    containsChinese(str) {
      return /[\u4e00-\u9fa5]/.test(str)
    },
    
    // 根据语言规则格式化姓名
    formatFullName(firstName, lastName) {
      // 如果任一字段包含中文，则视为中文名（姓在前，名在后，无空格）
      if (this.containsChinese(firstName) || this.containsChinese(lastName)) {
        return (lastName || '') + (firstName || '')
      }
      // 否则视为英文名（名在前，姓在后，有空格）
      return `${firstName || ''} ${lastName || ''}`.trim()
    },
    
    // 格式化日期时间
    formatDateTime(dateTimeString) {
      return new Date(dateTimeString).toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      })
    }
  }
}
</script>

<style scoped>
/* 所有样式已移至home.css */
</style>