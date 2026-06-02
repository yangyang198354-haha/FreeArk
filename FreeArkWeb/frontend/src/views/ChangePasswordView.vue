<template>
  <div class="change-password-view">
    <div class="page-head">
      <div class="ph-accent"></div>
      <div class="ph-text">
        <h2 class="ph-title">修改登录密码</h2>
        <p class="ph-sub">修改当前登录账号的密码</p>
      </div>
    </div>

    <el-card>
      <el-form :model="passwordForm" label-width="110px" label-position="right" @submit.prevent="handleSubmit">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="当前密码">
              <el-input v-model="passwordForm.currentPassword" type="password" show-password autocomplete="current-password" placeholder="请输入当前密码" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="新密码">
              <el-input v-model="passwordForm.newPassword" type="password" show-password autocomplete="new-password" placeholder="至少8位，包含字母、数字和特殊字符" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="确认新密码">
              <el-input v-model="passwordForm.confirmNewPassword" type="password" show-password autocomplete="new-password" placeholder="请再次输入新密码" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleSubmit">保存更改</el-button>
        </el-form-item>
        <el-alert v-if="message.text" :type="message.type" :title="message.text" show-icon :closable="false" style="margin-top:12px;" />
      </el-form>
    </el-card>
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
    const passwordForm = ref({ currentPassword: '', newPassword: '', confirmNewPassword: '' })
    const message = ref({ text: '', type: 'info' })

    const handleSubmit = async () => {
      if (passwordForm.value.newPassword !== passwordForm.value.confirmNewPassword) { message.value = { text: '新密码和确认新密码不一致', type: 'error' }; return }
      if (passwordForm.value.newPassword.length < 8) { message.value = { text: '新密码必须至少8位', type: 'error' }; return }
      const passwordRegex = /^(?=.*[a-zA-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/
      if (!passwordRegex.test(passwordForm.value.newPassword)) { message.value = { text: '新密码必须包含字母、数字和特殊字符', type: 'error' }; return }
      loading.value = true; message.value = { text: '', type: 'info' }
      try {
        const response = await api.post('/api/change-password/', { current_password: passwordForm.value.currentPassword, new_password: passwordForm.value.newPassword })
        if (response.success) {
          message.value = { text: '密码修改成功', type: 'success' }
          passwordForm.value = { currentPassword: '', newPassword: '', confirmNewPassword: '' }
          setTimeout(() => router.push('/home'), 1500)
        } else { message.value = { text: '密码修改失败', type: 'error' } }
      } catch (error) { console.error('修改密码失败:', error); message.value = { text: '密码修改失败，请检查当前密码是否正确', type: 'error' } }
      finally { loading.value = false }
    }

    return { passwordForm, loading, message, handleSubmit }
  }
}
</script>

<style scoped>
.change-password-view { padding: 0; }
.page-head { display: flex; align-items: flex-start; gap: 14px; margin-bottom: 20px; }
.ph-accent { width: 4px; height: 44px; border-radius: 2px; background: linear-gradient(180deg, var(--acc), var(--acc-2)); flex-shrink: 0; margin-top: 2px; }
.ph-title { margin: 0; font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--ink-0); line-height: 1.3; }
.ph-sub { margin: 4px 0 0 0; font-size: var(--font-size-sm); color: var(--ink-2); }
</style>
