<template>
  <!-- MOD-UI-001-D: 根容器改为 .create-user-view，无 background/shadow（由 Layout .content-wrapper 提供） -->
  <div class="create-user-view">
    <div class="page-header">
      <h2>创建用户</h2>
    </div>

    <!-- MOD-UI-001-D: .card > .card-body 替换为 el-card；原生表单控件替换为 Element Plus 组件 -->
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
              <el-input
                v-model="userForm.password"
                type="password"
                placeholder="至少8位，包含字母和数字"
                show-password
                autocomplete="new-password"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="确认密码" prop="confirmPassword">
              <el-input
                v-model="userForm.confirmPassword"
                type="password"
                placeholder="请再次输入密码"
                show-password
                autocomplete="new-password"
              />
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

    const userForm = reactive({
      username: '',
      email: '',
      firstName: '',
      lastName: '',
      password: '',
      confirmPassword: '',
      role: 'user',
      department: '',
      position: ''
    })

    // 密码复杂度校验（业务逻辑与原版一致：至少8位，包含字母和数字）
    function validatePassword(rule, value, callback) {
      if (!value) {
        callback(new Error('请输入密码'))
        return
      }
      const hasLetter = /[A-Za-z]/.test(value)
      const hasNumber = /[0-9]/.test(value)
      if (value.length < 8 || !hasLetter || !hasNumber) {
        callback(new Error('密码必须至少8位，包含字母和数字'))
      } else {
        callback()
      }
    }

    function validateConfirmPassword(rule, value, callback) {
      if (!value) {
        callback(new Error('请确认密码'))
        return
      }
      if (value !== userForm.password) {
        callback(new Error('密码和确认密码不一致'))
      } else {
        callback()
      }
    }

    const formRules = {
      username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
      email: [
        { required: true, message: '请输入电子邮箱', trigger: 'blur' },
        { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }
      ],
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
          // 转换请求体字段名（与原版保持一致）
          const userData = {
            username: userForm.username,
            email: userForm.email,
            first_name: userForm.firstName,
            last_name: userForm.lastName,
            password: userForm.password,
            role: userForm.role,
            department: userForm.department,
            position: userForm.position
          }

          const response = await api.post('/api/users/create/', userData)

          if (response) {
            ElMessage.success('用户创建成功')
            resetForm()
          } else {
            ElMessage.error('用户创建失败')
          }
        } catch (error) {
          console.error('创建用户失败:', error)
          const errorMessage = error.response?.data?.error || error.response?.data?.message || '用户创建失败，请检查输入信息'
          ElMessage.error(errorMessage)
        } finally {
          loading.value = false
        }
      })
    }

    function resetForm() {
      userForm.username = ''
      userForm.email = ''
      userForm.firstName = ''
      userForm.lastName = ''
      userForm.password = ''
      userForm.confirmPassword = ''
      userForm.role = 'user'
      userForm.department = ''
      userForm.position = ''
      if (createFormRef.value) {
        createFormRef.value.clearValidate()
      }
    }

    return {
      createFormRef,
      userForm,
      formRules,
      loading,
      handleSubmit,
      resetForm
    }
  }
}
</script>

<style scoped>
/* MOD-UI-001-D: 根容器无 background/shadow/padding，由 Layout .content-wrapper 提供 */
.create-user-view {
  padding: 0;
}
</style>
