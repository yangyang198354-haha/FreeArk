<template>
  <div class="page-container">
    <div class="page-header">
      <h2>创建用户</h2>
    </div>
    
    <!-- 用户创建表单 -->
    <div class="card">
      <div class="card-body">
        <form id="createUserForm" @submit.prevent="handleSubmit">
          <div class="form-row">
            <div class="form-group col-md-6">
              <label for="username">用户名 *</label>
              <input type="text" class="form-control" id="username" v-model="userForm.username" required>
            </div>
            <div class="form-group col-md-6">
              <label for="email">电子邮箱 *</label>
              <input type="email" class="form-control" id="email" v-model="userForm.email" required>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group col-md-6">
              <label for="firstName">名字 *</label>
              <input type="text" class="form-control" id="firstName" v-model="userForm.firstName" required>
            </div>
            <div class="form-group col-md-6">
              <label for="lastName">姓氏 *</label>
              <input type="text" class="form-control" id="lastName" v-model="userForm.lastName" required>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group col-md-6">
              <label for="password">密码 *</label>
              <input type="password" class="form-control" id="password" v-model="userForm.password" required autocomplete="new-password">
              <small class="form-text text-muted">密码必须至少8位，包含字母、数字和特殊字符</small>
            </div>
            <div class="form-group col-md-6">
              <label for="confirmPassword">确认密码 *</label>
              <input type="password" class="form-control" id="confirmPassword" v-model="userForm.confirmPassword" required autocomplete="new-password">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group col-md-6">
              <label for="role">角色</label>
              <select class="form-control" id="role" v-model="userForm.role">
                <option value="user">普通用户</option>
                <option value="admin">管理员</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group col-md-6">
              <label for="department">部门</label>
              <input type="text" class="form-control" id="department" v-model="userForm.department">
            </div>
            <div class="form-group col-md-6">
              <label for="position">职位</label>
              <input type="text" class="form-control" id="position" v-model="userForm.position">
            </div>
          </div>
          <button type="submit" class="btn btn-primary" :disabled="loading">创建用户</button>
          <div id="createUserMessage" class="mt-3"></div>
        </form>
      </div>
    </div>
  </div>
</template>

<script>
import { userApi } from '../services/api'

export default {
  name: 'CreateUserView',
  data() {
    return {
      userForm: {
        username: '',
        email: '',
        firstName: '',
        lastName: '',
        password: '',
        confirmPassword: '',
        role: 'user',
        department: '',
        position: ''
      },
      loading: false,
      message: '',
      messageType: ''
    }
  },
  methods: {
    // 验证密码规则
    validatePassword(password) {
      // 至少8位，包含字母和数字
      const hasLetter = /[A-Za-z]/.test(password)
      const hasNumber = /[0-9]/.test(password)
      const isValidLength = password.length >= 8
      
      return isValidLength && hasLetter && hasNumber
    },
    
    async handleSubmit() {
      // 表单验证
      if (this.userForm.password !== this.userForm.confirmPassword) {
        this.showMessage('密码和确认密码不一致', 'error')
        return
      }
      
      // 密码复杂度验证
      if (!this.validatePassword(this.userForm.password)) {
        this.showMessage('密码必须至少8位，包含字母和数字', 'error')
        return
      }
      
      this.loading = true
      this.clearMessage()
      
      try {
        // 转换请求体字段名
        const userData = {
          username: this.userForm.username,
          email: this.userForm.email,
          first_name: this.userForm.firstName,
          last_name: this.userForm.lastName,
          password: this.userForm.password,
          role: this.userForm.role,
          department: this.userForm.department,
          position: this.userForm.position
        }
        
        // 调用API创建用户
        const response = await userApi.createUser(userData)
        
        // 处理响应
        if (response.data) {
          this.showMessage('用户创建成功', 'success')
          // 重置表单
          this.resetForm()
        } else {
          this.showMessage('用户创建失败', 'error')
        }
      } catch (error) {
        console.error('创建用户失败:', error)
        // 提取错误信息
        const errorMessage = error.response?.data?.error || error.response?.data?.message || '用户创建失败，请检查输入信息'
        this.showMessage(errorMessage, 'error')
      } finally {
        this.loading = false
      }
    },
    
    resetForm() {
      this.userForm = {
        username: '',
        email: '',
        firstName: '',
        lastName: '',
        password: '',
        confirmPassword: '',
        role: 'user',
        department: '',
        position: ''
      }
    },
    
    showMessage(message, type) {
      const messageElement = document.getElementById('createUserMessage')
      messageElement.textContent = message
      messageElement.className = `mt-3 alert alert-${type}`
    },
    
    clearMessage() {
      const messageElement = document.getElementById('createUserMessage')
      messageElement.textContent = ''
      messageElement.className = 'mt-3'
    }
  }
}
</script>

<style scoped>
/* 所有样式已移至home.css */
</style>