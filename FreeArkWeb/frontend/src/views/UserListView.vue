<template>
  <div class="user-list-view">
    <div class="page-head">
      <div class="ph-accent"></div>
      <div class="ph-text">
        <h2 class="ph-title">用户列表</h2>
        <p class="ph-sub">管理系统登录账号</p>
      </div>
    </div>

    <el-card v-loading="loading">
      <el-table :data="users" stripe style="width: 100%;" empty-text="暂无用户数据">
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="email" label="电子邮箱" min-width="180" show-overflow-tooltip />
        <el-table-column label="姓名" min-width="120">
          <template #default="{ row }">{{ formatFullName(row.first_name, row.last_name) }}</template>
        </el-table-column>
        <el-table-column label="角色" width="100">
          <template #default="{ row }">{{ roleLabel(row.role) }}</template>
        </el-table-column>
        <el-table-column prop="department" label="部门" min-width="120" show-overflow-tooltip />
        <el-table-column prop="position" label="职位" min-width="120" show-overflow-tooltip />
        <el-table-column label="创建时间" min-width="160">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
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
  data() { return { users: [], loading: false } },
  mounted() { this.loadUsers() },
  methods: {
    async loadUsers() {
      this.loading = true
      try { const response = await api.get('/api/users/'); if (response) this.users = response }
      catch (error) { console.error('加载用户列表失败:', error); ElMessage.error('加载用户列表失败') }
      finally { this.loading = false }
    },
    // v1.6.0：角色英文值 → 中文名（admin/operator/user）
    roleLabel(role) { return { admin: '管理员', operator: '运维人员', user: '普通业主' }[role] || role || '—' },
    editUser(userId) { this.$router.push(`/edit-user/${userId}`) },
    async deleteUser(userId) {
      try { await ElMessageBox.confirm('确定要删除这个用户吗？', '提示', { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' }); await api.delete(`/api/users/${userId}/`); ElMessage.success('用户删除成功'); this.loadUsers() }
      catch (error) { if (error === 'cancel') return; console.error('删除用户失败:', error); ElMessage.error('删除用户失败') }
    },
    containsChinese(str) { return /[一-龥]/.test(str) },
    formatFullName(firstName, lastName) {
      if (this.containsChinese(firstName) || this.containsChinese(lastName)) return (lastName || '') + (firstName || '')
      return `${firstName || ''} ${lastName || ''}`.trim()
    },
    formatDateTime(dateTimeString) {
      return new Date(dateTimeString).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
    }
  }
}
</script>

<style scoped>
.user-list-view { padding: 0; }
.page-head { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 20px; }
.ph-accent { width: 4px; height: 44px; border-radius: 2px; background: linear-gradient(180deg, var(--acc), var(--acc-2)); flex-shrink: 0; margin-top: 2px; }
.ph-title { margin: 0; font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--ink-0); line-height: 1.3; }
.ph-sub { margin: 4px 0 0 0; font-size: var(--font-size-sm); color: var(--ink-2); }
</style>
