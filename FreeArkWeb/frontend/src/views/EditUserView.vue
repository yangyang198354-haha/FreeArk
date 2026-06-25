<template>
  <div class="edit-user-view">
    <div class="page-head">
      <div class="ph-accent"></div>
      <div class="ph-text">
        <h2 class="ph-title">编辑用户</h2>
        <p class="ph-sub">修改用户信息</p>
      </div>
    </div>

    <el-card v-loading="loading">
      <el-form :model="userForm" label-width="120px" label-position="right" @submit.prevent="handleSubmit">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="用户名">
              <el-input v-model="userForm.username" readonly />
              <div class="field-hint">用户名不可修改</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="电子邮箱">
              <el-input v-model="userForm.email" type="email" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="名字">
              <el-input v-model="userForm.firstName" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="姓氏">
              <el-input v-model="userForm.lastName" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="密码">
              <el-input v-model="userForm.password" type="password" placeholder="留空表示不修改密码" show-password autocomplete="current-password" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="角色">
              <el-select v-model="userForm.role" disabled style="width:100%;">
                <el-option label="管理员" value="admin" />
                <el-option label="运维人员" value="operator" />
                <el-option label="普通业主" value="user" />
              </el-select>
              <div class="field-hint">角色不可修改</div>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="部门">
              <el-input v-model="userForm.department" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="职位">
              <el-input v-model="userForm.position" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item>
          <el-button @click="goBack">取消</el-button>
          <el-button type="primary" :loading="loading" @click="handleSubmit">保存更改</el-button>
        </el-form-item>
        <el-alert v-if="message.text" :type="message.type" :title="message.text" show-icon :closable="false" style="margin-top:12px;" />
      </el-form>
    </el-card>
  </div>
</template>

<script>
import api from '@/utils/api.js'
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'

export default {
  name: 'EditUserView',
  setup() {
    const route = useRoute()
    const userId = ref('')
    const userForm = ref({ username: '', email: '', firstName: '', lastName: '', password: '', role: 'user', department: '', position: '' })
    const loading = ref(false)
    const message = ref({ text: '', type: 'info' })

    onMounted(() => {
      const id = route.params.id
      if (id) { userId.value = id; loadUser(id) }
      else { message.value = { text: '未找到用户ID', type: 'error' } }
    })

    watch(() => route.params.id, (newId) => { if (newId) { userId.value = newId; loadUser(newId) } })

    const loadUser = async (id) => {
      loading.value = true
      try {
        const response = await api.get(`/api/users/${id}/`)
        if (response) {
          userForm.value = { username: response.username, email: response.email, firstName: response.first_name, lastName: response.last_name, password: '', role: response.role, department: response.department, position: response.position }
        }
      } catch (error) { console.error('加载用户信息失败:', error); message.value = { text: '加载用户信息失败', type: 'error' } }
      finally { loading.value = false }
    }

    const handleSubmit = async () => {
      loading.value = true; message.value = { text: '', type: 'info' }
      try {
        const updateData = { email: userForm.value.email, first_name: userForm.value.firstName, last_name: userForm.value.lastName, department: userForm.value.department, position: userForm.value.position }
        if (userForm.value.password) updateData.password = userForm.value.password
        const response = await api.patch(`/api/users/${userId.value}/`, updateData)
        if (response) message.value = { text: '用户更新成功', type: 'success' }
        else message.value = { text: '用户更新失败', type: 'error' }
      } catch (error) { console.error('更新用户失败:', error); message.value = { text: '用户更新失败，请检查输入信息', type: 'error' } }
      finally { loading.value = false }
    }

    const goBack = () => { window.history.back() }

    return { userId, userForm, loading, message, handleSubmit, goBack }
  }
}
</script>

<style scoped>
.edit-user-view { padding: 0; }
.page-head { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 20px; }
.ph-accent { width: 4px; height: 44px; border-radius: 2px; background: linear-gradient(180deg, var(--acc), var(--acc-2)); flex-shrink: 0; margin-top: 2px; }
.ph-title { margin: 0; font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--ink-0); line-height: 1.3; }
.ph-sub { margin: 4px 0 0 0; font-size: var(--font-size-sm); color: var(--ink-2); }
.field-hint { font-size: var(--font-size-sm); color: var(--ink-2); margin-top: 4px; }
</style>
