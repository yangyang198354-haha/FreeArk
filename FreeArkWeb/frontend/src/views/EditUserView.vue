<template>
  <div class="page-container">
    <div class="page-header">
      <h2 id="editUserPageTitle">编辑用户</h2>
      <button type="button" class="btn btn-secondary" @click="goBack">返回用户列表</button>
    </div>
    
    <div class="card">
      <div class="card-body">
        <form id="editUserForm" @submit.prevent="handleSubmit">
          <input type="hidden" id="editUserId" v-model="userId">
          <div class="form-row">
            <div class="form-group col-md-6">
              <label for="editUsername">用户名 *</label>
              <input type="text" class="form-control" id="editUsername" v-model="userForm.username" readonly>
              <small class="form-text text-muted">用户名不可修改</small>
            </div>
            <div class="form-group col-md-6">
              <label for="editEmail">电子邮箱 *</label>
              <input type="email" class="form-control" id="editEmail" v-model="userForm.email">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group col-md-6">
              <label for="editFirstName">名字</label>
              <input type="text" class="form-control" id="editFirstName" v-model="userForm.firstName">
            </div>
            <div class="form-group col-md-6">
              <label for="editLastName">姓氏</label>
              <input type="text" class="form-control" id="editLastName" v-model="userForm.lastName">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group col-md-6">
              <label for="editPassword">密码 (留空表示不修改)</label>
              <input type="password" class="form-control" id="editPassword" v-model="userForm.password" placeholder="留空表示不修改密码" autocomplete="current-password">
            </div>
            <div class="form-group col-md-6">
              <label for="editRole">角色</label>
              <select class="form-control" id="editRole" v-model="userForm.role" disabled>
                <option value="user">普通用户</option>
                <option value="admin">管理员</option>
              </select>
              <small class="form-text text-muted">角色不可修改</small>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group col-md-6">
              <label for="editDepartment">部门</label>
              <input type="text" class="form-control" id="editDepartment" v-model="userForm.department">
            </div>
            <div class="form-group col-md-6">
              <label for="editPosition">职位</label>
              <input type="text" class="form-control" id="editPosition" v-model="userForm.position">
            </div>
          </div>
          <div class="form-group">
            <button type="button" class="btn btn-secondary mr-2" @click="goBack">取消</button>
            <button type="submit" class="btn btn-primary" :disabled="loading">保存更改</button>
          </div>
          <input type="submit" style="display: none;">
          <div id="editUserMessage" class="mt-3"></div>
        </form>
      </div>
    </div>
  </div>
</template>

<script>
import { userApi } from '../services/api'
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'

export default {
  name: 'EditUserView',
  setup() {
    const route = useRoute()
    const userId = ref('')
    const userForm = ref({
      username: '',
      email: '',
      firstName: '',
      lastName: '',
      password: '',
      role: 'user',
      department: '',
      position: ''
    })
    const loading = ref(false)
    const message = ref('')

    onMounted(() => {
      // 获取URL中的用户ID
      console.log('Route params:', route.params)
      const id = route.params.id
      if (id) {
        userId.value = id
        loadUser(id)
      } else {
        console.error('No userId found in route params')
        showMessage('未找到用户ID', 'error')
      }
    })

    // 监听路由参数变化
    watch(() => route.params.id, (newId) => {
      console.log('Route params id changed:', newId)
      if (newId) {
        userId.value = newId
        loadUser(newId)
      }
    })

    const loadUser = async (id) => {
      loading.value = true
      try {
        const response = await userApi.getUser(id)
        if (response.data) {
          const user = response.data
          userForm.value = {
            username: user.username,
            email: user.email,
            firstName: user.first_name,
            lastName: user.last_name,
            password: '',
            role: user.role,
            department: user.department,
            position: user.position
          }
        }
      } catch (error) {
        console.error('加载用户信息失败:', error)
        showMessage('加载用户信息失败', 'error')
      } finally {
        loading.value = false
      }
    }

    const handleSubmit = async () => {
      loading.value = true
      clearMessage()
      
      try {
        // 构建更新数据，只包含需要更新的字段
        const updateData = {
          email: userForm.value.email,
          first_name: userForm.value.firstName,
          last_name: userForm.value.lastName,
          department: userForm.value.department,
          position: userForm.value.position
        }
        
        // 如果密码不为空，则添加到更新数据中
        if (userForm.value.password) {
          updateData.password = userForm.value.password
        }
        
        // 调用API更新用户
        const response = await userApi.updateUser(userId.value, updateData)
        
        if (response.data) {
          showMessage('用户更新成功', 'success')
        } else {
          showMessage('用户更新失败', 'error')
        }
      } catch (error) {
        console.error('更新用户失败:', error)
        showMessage('用户更新失败，请检查输入信息', 'error')
      } finally {
        loading.value = false
      }
    }

    const goBack = () => {
      window.history.back()
    }

    const showMessage = (msg, type) => {
      const messageElement = document.getElementById('editUserMessage')
      messageElement.textContent = msg
      messageElement.className = `mt-3 alert alert-${type}`
    }

    const clearMessage = () => {
      const messageElement = document.getElementById('editUserMessage')
      messageElement.textContent = ''
      messageElement.className = 'mt-3'
    }

    return {
      userId,
      userForm,
      loading,
      message,
      handleSubmit,
      goBack
    }
  }
}
</script>

<style scoped>
/* 所有样式已移至home.css */
</style>