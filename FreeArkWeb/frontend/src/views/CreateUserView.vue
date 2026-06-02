<template>
  <div class="create-user-view">
    <div class="page-head">
      <div class="ph-accent"></div>
      <div class="ph-text">
        <h2 class="ph-title">创建用户</h2>
        <p class="ph-sub">为员工创建系统登录账号</p>
      </div>
    </div>

    <el-card>
      <el-form
        ref="createFormRef"
        :model="userForm"
        :rules="formRules"
        label-width="90px"
        label-position="right"
        @submit.prevent="handleSubmit"
      >
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="userForm.username" placeholder="请输入用户名" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="电子邮箱" prop="email">
              <el-input v-model="userForm.email" type="email" placeholder="请输入电子邮箱" clearable />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="名字" prop="firstName">
              <el-input v-model="userForm.firstName" placeholder="请输入名字" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="姓氏" prop="lastName">
              <el-input v-model="userForm.lastName" placeholder="请输入姓氏" clearable />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="密码" prop="password">
              <el-input v-model="userForm.password" type="password" placeholder="至少8位，包含字母和数字" show-password autocomplete="new-password" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="确认密码" prop="confirmPassword">
              <el-input v-model="userForm.confirmPassword" type="password" placeholder="请再次输入密码" show-password autocomplete="new-password" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="角色" prop="role">
              <el-select v-model="userForm.role" style="width: 100%;">
                <el-option label="普通用户" value="user" />
                <el-option label="管理员" value="admin" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="部门" prop="department">
              <el-input v-model="userForm.department" placeholder="请输入部门（选填）" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="职位" prop="position">
              <el-input v-model="userForm.position" placeholder="请输入职位（选填）" clearable />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleSubmit">创建用户</el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'

export default {
  name: 'CreateUserView',
  setup() {
    const createFormRef = ref(null)
    const loading = ref(false)
    const userForm = reactive({ username: '', email: '', firstName: '', lastName: '', password: '', confirmPassword: '', role: 'user', department: '', position: '' })

    function validatePassword(rule, value, callback) {
      if (!value) { callback(new Error('请输入密码')); return }
      if (value.length < 8 || !/[A-Za-z]/.test(value) || !/[0-9]/.test(value)) callback(new Error('密码必须至少8位，包含字母和数字'))
      else callback()
    }
    function validateConfirmPassword(rule, value, callback) {
      if (!value) { callback(new Error('请确认密码')); return }
      if (value !== userForm.password) callback(new Error('密码和确认密码不一致'))
      else callback()
    }

    const formRules = {
      username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
      email: [{ required: true, message: '请输入电子邮箱', trigger: 'blur' }, { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
      firstName: [{ required: true, message: '请输入名字', trigger: 'blur' }],
      lastName: [{ required: true, message: '请输入姓氏', trigger: 'blur' }],
      password: [{ required: true, validator: validatePassword, trigger: 'blur' }],
      confirmPassword: [{ required: true, validator: validateConfirmPassword, trigger: 'blur' }]
    }

    async function handleSubmit() {
      if (!createFormRef.value) return
      await createFormRef.value.validate(async (valid) => {
        if (!valid) return
        loading.value = true
        try {
          const userData = { username: userForm.username, email: userForm.email, first_name: userForm.firstName, last_name: userForm.lastName, password: userForm.password, role: userForm.role, department: userForm.department, position: userForm.position }
          const response = await api.post('/api/users/create/', userData)
          if (response) { ElMessage.success('用户创建成功'); resetForm() } else { ElMessage.error('用户创建失败') }
        } catch (error) {
          console.error('创建用户失败:', error)
          ElMessage.error(error.response?.data?.error || error.response?.data?.message || '用户创建失败，请检查输入信息')
        } finally { loading.value = false }
      })
    }

    function resetForm() {
      Object.assign(userForm, { username: '', email: '', firstName: '', lastName: '', password: '', confirmPassword: '', role: 'user', department: '', position: '' })
      if (createFormRef.value) createFormRef.value.clearValidate()
    }

    return { createFormRef, userForm, formRules, loading, handleSubmit, resetForm }
  }
}
</script>

<style scoped>
.create-user-view { padding: 0; }
.page-head { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 20px; }
.ph-accent { width: 4px; height: 44px; border-radius: 2px; background: linear-gradient(180deg, var(--acc), var(--acc-2)); flex-shrink: 0; margin-top: 2px; }
.ph-title { margin: 0; font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--ink-0); line-height: 1.3; }
.ph-sub { margin: 4px 0 0 0; font-size: var(--font-size-sm); color: var(--ink-2); }
</style>
