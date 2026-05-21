<template>
  <!-- MOD-UI-001-E: 根容器改为 .user-list-view，无 background/shadow（由 Layout .content-wrapper 提供） -->
  <div class="user-list-view">
    <div class="page-header">
      <h2>用户列表</h2>
    </div>

    <!-- MOD-UI-001-E: .card > .card-body 替换为 el-card；原生 <table> 替换为 el-table；操作按钮替换为 el-button -->
    <el-card v-loading="loading">
      <el-table
        :data="users"
        stripe
        style="width: 100%;"
        empty-text="暂无用户数据"
      >
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="email" label="电子邮箱" min-width="180" show-overflow-tooltip />
        <el-table-column label="姓名" min-width="120">
          <template #default="{ row }">
            {{ formatFullName(row.first_name, row.last_name) }}
          </template>
        </el-table-column>
        <el-table-column prop="role" label="角色" width="100" />
        <el-table-column prop="department" label="部门" min-width="120" show-overflow-tooltip />
        <el-table-column prop="position" label="职位" min-width="120" show-overflow-tooltip />
        <el-table-column label="创建时间" min-width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="editUser(row.id)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteUser(row.id)" style="margin-left: 4px;">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script>
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'

export default {
  name: 'UserListView',
  data() {
    return {
      users: [],
      loading: false
    }
  },
  mounted() {
    this.loadUsers()
  },
  methods: {
    async loadUsers() {
      this.loading = true
      try {
        const response = await api.get('/api/users/')
        if (response) {
          this.users = response
        }
      } catch (error) {
        console.error('加载用户列表失败:', error)
        ElMessage.error('加载用户列表失败')
      } finally {
        this.loading = false
      }
    },

    editUser(userId) {
      // 跳转到编辑用户页面（路由与原版保持一致）
      this.$router.push(`/edit-user/${userId}`)
    },

    async deleteUser(userId) {
      try {
        // 使用 el-message-box 替代原生 confirm（更符合 Element Plus 风格）
        await ElMessageBox.confirm('确定要删除这个用户吗？', '提示', {
          type: 'warning',
          confirmButtonText: '确定',
          cancelButtonText: '取消'
        })
        await api.delete(`/api/users/${userId}/`)
        ElMessage.success('用户删除成功')
        this.loadUsers()
      } catch (error) {
        if (error === 'cancel') return // 用户取消，不报错
        console.error('删除用户失败:', error)
        ElMessage.error('删除用户失败')
      }
    },

    // 判断字符串是否包含中文字符（与原版保持一致）
    containsChinese(str) {
      return /[一-龥]/.test(str)
    },

    // 根据语言规则格式化姓名（与原版保持一致）
    formatFullName(firstName, lastName) {
      if (this.containsChinese(firstName) || this.containsChinese(lastName)) {
        return (lastName || '') + (firstName || '')
      }
      return `${firstName || ''} ${lastName || ''}`.trim()
    },

    // 格式化日期时间（与原版保持一致）
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
/* MOD-UI-001-E: 根容器无 background/shadow/padding，由 Layout .content-wrapper 提供 */
.user-list-view {
  padding: 0;
}
</style>
