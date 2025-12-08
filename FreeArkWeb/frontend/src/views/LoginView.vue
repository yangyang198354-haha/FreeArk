<template>
  <div class="login-wrapper">
    <div class="login-container">
      <div class="login-header">
        <h2>自由方舟能耗采集平台登录</h2>
      </div>
      
      <el-form :model="loginForm" :rules="loginRules" ref="loginFormRef" label-position="top">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="loginForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <div v-if="error" class="error-message">
          {{ error }}
        </div>
        <el-form-item>
          <el-button type="primary" @click="handleLogin" :loading="loading" class="login-button">
            <span v-if="!loading">登录</span>
            <span v-else>登录中...</span>
          </el-button>
        </el-form-item>
      </el-form>
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
          { required: true, message: '请输入密码', trigger: 'blur' }
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
            // 使用axios默认配置，直接调用API
            const response = await axios.post('/api/auth/login/', this.loginForm, {
              withCredentials: true
            });
            
            // 登录成功
            if (response.data.token) {
              // 存储token到localStorage
              localStorage.setItem('userToken', response.data.token);
              localStorage.setItem('isAuthenticated', 'true');
              
              // 安全地设置cookie
              const cookieOptions = {
                path: '/',
                maxAge: 3600,
                sameSite: 'Lax',
                secure: window.location.protocol === 'https:'
              };
              
              let cookieString = `auth_token=${encodeURIComponent(response.data.token)}; path=${cookieOptions.path}; max-age=${cookieOptions.maxAge}`;
              if (cookieOptions.sameSite) cookieString += `; SameSite=${cookieOptions.sameSite}`;
              if (cookieOptions.secure) cookieString += '; Secure';
              
              document.cookie = cookieString;
              
              // 跳转到首页
              this.$router.push('/');
            }
          } catch (error) {
            let errorMessage = '登录失败，请检查用户名和密码';
            if (error.response) {
              errorMessage = error.response.data?.non_field_errors?.[0] || 
                           error.response.data?.detail || 
                           errorMessage;
            } else if (error.message.includes('NetworkError') || error.message.includes('Failed to fetch')) {
              errorMessage = '网络连接异常，请检查您的网络';
            }
            this.error = errorMessage;
          } finally {
            this.loading = false;
          }
        }
      })
    }
  }
}
</script>

<style scoped>
.login-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.login-container {
  background: white;
  padding: 2rem;
  border-radius: 8px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 400px;
}

.login-header {
  text-align: center;
  margin-bottom: 2rem;
}

.login-header h2 {
  color: #303133;
  font-size: 1.5rem;
  font-weight: 600;
}

.error-message {
  color: #f56c6c;
  font-size: 0.875rem;
  margin-bottom: 1rem;
  text-align: center;
}

.login-button {
  width: 100%;
  padding: 0.75rem;
  font-size: 1rem;
}
</style>