<template>
  <div class="page-container">
    <div class="page-header">
      <h2>修改登录密码</h2>
    </div>
    
    <!-- 修改密码表单 -->
    <div class="card">
      <div class="card-body">
        <form id="changePasswordForm" @submit.prevent="handleSubmit">
          <div class="form-row">
            <div class="form-group col-md-6">
              <label for="currentPassword">当前密码 *</label>
              <input type="password" class="form-control" id="currentPassword" v-model="passwordForm.currentPassword" required autocomplete="current-password">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group col-md-6">
              <label for="newPassword">新密码 *</label>
              <input type="password" class="form-control" id="newPassword" v-model="passwordForm.newPassword" required autocomplete="new-password">
              <small class="form-text text-muted">密码必须至少8位，包含字母、数字和特殊字符</small>
            </div>
            <div class="form-group col-md-6">
              <label for="confirmNewPassword">确认新密码 *</label>
              <input type="password" class="form-control" id="confirmNewPassword" v-model="passwordForm.confirmNewPassword" required autocomplete="new-password">
            </div>
          </div>
          <button type="submit" class="btn btn-primary" :disabled="loading">保存更改</button>
          <div id="changePasswordMessage" class="mt-3"></div>
        </form>
      </div>
    </div>
  </div>
</template>

<script>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/utils/api.js'

export default {
  name: 'ChangePasswordView',
  setup() {
    const router = useRouter()
    const loading = ref(false)
    
    const passwordForm = ref({
      currentPassword: '',
      newPassword: '',
      confirmNewPassword: ''
    })
    
    const showMessage = (message, type) => {
      const messageElement = document.getElementById('changePasswordMessage')
      messageElement.textContent = message
      messageElement.className = `mt-3 alert alert-${type}`
    }
    
    const clearMessage = () => {
      const messageElement = document.getElementById('changePasswordMessage')
      messageElement.textContent = ''
      messageElement.className = 'mt-3'
    }
    
    const handleSubmit = async () => {
      // 表单验证
      if (passwordForm.value.newPassword !== passwordForm.value.confirmNewPassword) {
        showMessage('新密码和确认新密码不一致', 'error')
        return
      }
      
      if (passwordForm.value.newPassword.length < 8) {
        showMessage('新密码必须至少8位', 'error')
        return
      }
      
      // 检查密码复杂度
      const passwordRegex = /^(?=.*[a-zA-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/
      if (!passwordRegex.test(passwordForm.value.newPassword)) {
        showMessage('新密码必须包含字母、数字和特殊字符', 'error')
        return
      }
      
      loading.value = true
      clearMessage()
      
      try {
        // 调用API修改密码
        const response = await api.post('/api/change-password/', {
          current_password: passwordForm.value.currentPassword,
          new_password: passwordForm.value.newPassword
        })
        
        if (response.success) {
          showMessage('密码修改成功', 'success')
          // 重置表单
          passwordForm.value = {
            currentPassword: '',
            newPassword: '',
            confirmNewPassword: ''
          }
          // 延迟后跳转回首页
          setTimeout(() => {
            router.push('/home')
          }, 1500)
        } else {
          showMessage('密码修改失败', 'error')
        }
      } catch (error) {
        console.error('修改密码失败:', error)
        showMessage('密码修改失败，请检查当前密码是否正确', 'error')
      } finally {
        loading.value = false
      }
    }
    
    return {
      passwordForm,
      loading,
      handleSubmit
    }
  }
}
</script>

<style scoped>
/* 所有样式已移至home.css */
</style>