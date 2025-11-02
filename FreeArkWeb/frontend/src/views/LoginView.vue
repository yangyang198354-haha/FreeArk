<template>
  <div class="login-container">
    <div class="login-form-wrapper">
      <h2>FreeArk 系统登录</h2>
      <el-form :model="loginForm" :rules="loginRules" ref="loginFormRef" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="loginForm.username" placeholder="请输入用户名" prefix-icon="el-icon-user" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" prefix-icon="el-icon-lock" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleLogin" :loading="loading" style="width: 100%">登录</el-button>
        </el-form-item>
      </el-form>
      <div v-if="error" class="error-message">
        {{ error }}
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'LoginView',
  data() {
    return {
      loginForm: {
        username: '',
        password: ''
      },
      loginRules: {
        username: [
          { required: true, message: '请输入用户名', trigger: 'blur' }
        ],
        password: [
          { required: true, message: '请输入密码', trigger: 'blur' },
          { min: 6, message: '密码长度至少为6位', trigger: 'blur' }
        ]
      },
      loading: false,
      error: ''
    }
  },
  methods: {
    async handleLogin() {
      this.$refs.loginFormRef.validate(async (valid) => {
        if (valid) {
          this.loading = true
          this.error = ''
          try {
            const response = await axios.post('http://localhost:8000/api/auth/login/', this.loginForm, {
              headers: {
                'Content-Type': 'application/json'
              },
              withCredentials: true
            })
            
            // 存储用户信息和Token
            if (response.data.token) {
              localStorage.setItem('userToken', response.data.token)
            }
            localStorage.setItem('userInfo', JSON.stringify(response.data.user || response.data.success ? response.data : {}))
            localStorage.setItem('isAuthenticated', 'true')
            
            // 显示成功消息并跳转到首页
            this.$message.success('登录成功！')
            this.$router.push('/')
          } catch (error) {
            this.error = error.response?.data?.non_field_errors?.[0] || 
                        error.response?.data?.detail || 
                        '登录失败，请检查用户名和密码'
          } finally {
            this.loading = false
          }
        }
      })
    }
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background-color: #f5f7fa;
}

.login-form-wrapper {
  background-color: white;
  padding: 40px;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  width: 400px;
}

.login-form-wrapper h2 {
  text-align: center;
  margin-bottom: 30px;
  color: #303133;
}

.error-message {
  color: #f56c6c;
  margin-top: 15px;
  text-align: center;
}
</style>