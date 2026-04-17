<template>
  <div class="page-container">
    <div class="page-header">
      <h2>业主管理</h2>
    </div>

    <!-- 搜索过滤栏 -->
    <div class="card" style="margin-bottom: 16px;">
      <div class="card-body">
        <el-form :inline="true" :model="searchForm" class="search-form">
          <el-form-item label="楼栋">
            <el-select
              v-model="searchForm.building"
              placeholder="全部楼栋"
              clearable
              style="width: 120px;"
              @change="onBuildingChange"
            >
              <el-option
                v-for="b in buildingOptions"
                :key="b"
                :label="b"
                :value="b"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="单元">
            <el-select
              v-model="searchForm.unit"
              placeholder="全部单元"
              clearable
              style="width: 120px;"
            >
              <el-option
                v-for="u in unitOptions"
                :key="u"
                :label="u"
                :value="u"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="绑定状态">
            <el-select
              v-model="searchForm.bind_status"
              placeholder="全部状态"
              clearable
              style="width: 120px;"
            >
              <el-option label="已绑定" value="已绑定" />
              <el-option label="未绑定" value="未绑定" />
            </el-select>
          </el-form-item>
          <el-form-item label="关键词">
            <el-input
              v-model="searchForm.search"
              placeholder="专有部分/坐落/户号"
              clearable
              style="width: 200px;"
              @keyup.enter="handleSearch"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleSearch">搜索</el-button>
            <el-button @click="handleReset">重置</el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>

    <!-- 操作栏 -->
    <div class="card">
      <div class="card-body">
        <div style="margin-bottom: 12px;" v-if="isAdmin">
          <el-button type="primary" @click="openCreateDialog">新增业主</el-button>
        </div>

        <!-- 数据表格 -->
        <el-table
          :data="ownerList"
          v-loading="loading"
          stripe
          style="width: 100%;"
          empty-text="暂无数据"
        >
          <el-table-column prop="specific_part" label="专有部分" width="120" fixed />
          <el-table-column prop="location_name" label="坐落" min-width="200" show-overflow-tooltip />
          <el-table-column prop="building" label="楼栋" width="80" />
          <el-table-column prop="unit" label="单元" width="80" />
          <el-table-column prop="floor" label="楼层" width="80" />
          <el-table-column prop="room_number" label="户号" width="80" />
          <el-table-column prop="bind_status" label="绑定状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.bind_status === '已绑定' ? 'success' : 'info'" size="small">
                {{ row.bind_status || '—' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="ip_address" label="IP地址" width="130" />
          <el-table-column prop="plc_ip_address" label="PLC IP" width="130" />
          <el-table-column prop="unique_id" label="唯一标识符" width="160" show-overflow-tooltip />
          <el-table-column label="操作" width="150" fixed="right" v-if="isAdmin">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="openEditDialog(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="deleteOwner(row.id)" style="margin-left: 6px;">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 分页 -->
        <div style="margin-top: 16px; display: flex; justify-content: flex-end;">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            :total="total"
            @size-change="handlePageSizeChange"
            @current-change="handlePageChange"
          />
        </div>
      </div>
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新增业主' : '编辑业主'"
      width="600px"
      :close-on-click-modal="false"
      @close="resetForm"
    >
      <el-form
        ref="ownerFormRef"
        :model="ownerForm"
        :rules="formRules"
        label-width="110px"
        label-position="right"
      >
        <el-form-item label="专有部分" prop="specific_part">
          <el-input
            v-model="ownerForm.specific_part"
            placeholder="如：1-1-2-201"
            :disabled="dialogMode === 'edit'"
          />
        </el-form-item>
        <el-form-item label="坐落" prop="location_name">
          <el-input v-model="ownerForm.location_name" placeholder="如：成都乐府（二仙桥）-1-1-201" />
        </el-form-item>
        <el-form-item label="楼栋" prop="building">
          <el-input v-model="ownerForm.building" placeholder="如：1栋" />
        </el-form-item>
        <el-form-item label="单元" prop="unit">
          <el-input v-model="ownerForm.unit" placeholder="如：1单元" />
        </el-form-item>
        <el-form-item label="楼层" prop="floor">
          <el-input v-model="ownerForm.floor" placeholder="如：2楼" />
        </el-form-item>
        <el-form-item label="户号" prop="room_number">
          <el-input v-model="ownerForm.room_number" placeholder="如：201" />
        </el-form-item>
        <el-form-item label="绑定状态" prop="bind_status">
          <el-select v-model="ownerForm.bind_status" placeholder="请选择" style="width: 100%;">
            <el-option label="已绑定" value="已绑定" />
            <el-option label="未绑定" value="未绑定" />
          </el-select>
        </el-form-item>
        <el-form-item label="IP地址" prop="ip_address">
          <el-input v-model="ownerForm.ip_address" placeholder="如：192.168.1.4" />
        </el-form-item>
        <el-form-item label="唯一标识符" prop="unique_id">
          <el-input v-model="ownerForm.unique_id" placeholder="如：89dbe11564b1a4e0" />
        </el-form-item>
        <el-form-item label="PLC IP地址" prop="plc_ip_address">
          <el-input v-model="ownerForm.plc_ip_address" placeholder="如：192.168.1.5" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import api from '@/utils/api.js'
import { ElMessage, ElMessageBox } from 'element-plus'

export default {
  name: 'OwnerManagementView',
  data() {
    return {
      // 列表数据
      ownerList: [],
      total: 0,
      currentPage: 1,
      pageSize: 20,
      loading: false,

      // 搜索
      searchForm: {
        building: '',
        unit: '',
        bind_status: '',
        search: ''
      },

      // 下拉选项（动态填充）
      buildingOptions: [],
      unitOptions: [],

      // 弹窗
      dialogVisible: false,
      dialogMode: 'create', // 'create' | 'edit'
      submitting: false,
      editingId: null,

      // 表单
      ownerForm: {
        specific_part: '',
        location_name: '',
        building: '',
        unit: '',
        floor: '',
        room_number: '',
        bind_status: '已绑定',
        ip_address: '',
        unique_id: '',
        plc_ip_address: ''
      },

      // 表单校验规则
      formRules: {
        specific_part: [
          { required: true, message: '请输入专有部分标识符', trigger: 'blur' },
          { max: 20, message: '最多 20 个字符', trigger: 'blur' }
        ],
        building: [
          { required: true, message: '请输入楼栋', trigger: 'blur' }
        ],
        unit: [
          { required: true, message: '请输入单元', trigger: 'blur' }
        ],
        room_number: [
          { required: true, message: '请输入户号', trigger: 'blur' }
        ]
      },

      // 当前用户角色
      userRole: 'user'
    }
  },

  computed: {
    isAdmin() {
      return this.userRole === 'admin'
    }
  },

  mounted() {
    // 从 localStorage 读取用户角色
    try {
      const userInfo = JSON.parse(localStorage.getItem('userInfo') || '{}')
      this.userRole = userInfo.role || 'user'
    } catch (e) {
      this.userRole = 'user'
    }
    this.loadOwners()
    this.loadFilterOptions()
  },

  methods: {
    // 加载业主列表
    async loadOwners() {
      this.loading = true
      try {
        const params = new URLSearchParams({
          page: this.currentPage,
          page_size: this.pageSize
        })
        if (this.searchForm.building) params.append('building', this.searchForm.building)
        if (this.searchForm.unit) params.append('unit', this.searchForm.unit)
        if (this.searchForm.bind_status) params.append('bind_status', this.searchForm.bind_status)
        if (this.searchForm.search) params.append('search', this.searchForm.search)

        const response = await api.get(`/api/owners/?${params.toString()}`)
        if (response && response.success) {
          this.ownerList = response.data
          this.total = response.total
        }
      } catch (error) {
        console.error('加载业主列表失败：', error)
        ElMessage.error('加载业主列表失败，请稍后重试')
      } finally {
        this.loading = false
      }
    },

    // 加载楼栋/单元下拉选项（首次加载全量列表时提取）
    async loadFilterOptions() {
      try {
        // 请求较大 page_size 拉取所有记录的楼栋/单元字段
        const response = await api.get('/api/owners/?page=1&page_size=1000')
        if (response && response.data) {
          const buildings = [...new Set(response.data.map(o => o.building).filter(Boolean))].sort()
          const units = [...new Set(response.data.map(o => o.unit).filter(Boolean))].sort()
          this.buildingOptions = buildings
          this.unitOptions = units
        }
      } catch (e) {
        // 静默失败，不影响主流程
      }
    },

    // 楼栋变化时重置单元
    onBuildingChange() {
      this.searchForm.unit = ''
    },

    // 搜索
    handleSearch() {
      this.currentPage = 1
      this.loadOwners()
    },

    // 重置搜索
    handleReset() {
      this.searchForm = { building: '', unit: '', bind_status: '', search: '' }
      this.currentPage = 1
      this.loadOwners()
    },

    // 分页变化
    handlePageChange(page) {
      this.currentPage = page
      this.loadOwners()
    },

    handlePageSizeChange(size) {
      this.pageSize = size
      this.currentPage = 1
      this.loadOwners()
    },

    // 打开新增弹窗
    openCreateDialog() {
      this.dialogMode = 'create'
      this.editingId = null
      this.resetForm()
      this.dialogVisible = true
    },

    // 打开编辑弹窗
    async openEditDialog(row) {
      this.dialogMode = 'edit'
      this.editingId = row.id
      this.resetForm()
      try {
        const response = await api.get(`/api/owners/${row.id}/`)
        if (response && response.success) {
          const d = response.data
          this.ownerForm = {
            specific_part: d.specific_part || '',
            location_name: d.location_name || '',
            building: d.building || '',
            unit: d.unit || '',
            floor: d.floor || '',
            room_number: d.room_number || '',
            bind_status: d.bind_status || '已绑定',
            ip_address: d.ip_address || '',
            unique_id: d.unique_id || '',
            plc_ip_address: d.plc_ip_address || ''
          }
        }
      } catch (error) {
        ElMessage.error('获取业主信息失败')
        return
      }
      this.dialogVisible = true
    },

    // 提交表单
    async submitForm() {
      try {
        await this.$refs.ownerFormRef.validate()
      } catch (e) {
        return
      }

      this.submitting = true
      try {
        let response
        if (this.dialogMode === 'create') {
          response = await api.post('/api/owners/', this.ownerForm)
        } else {
          response = await api.patch(`/api/owners/${this.editingId}/`, this.ownerForm)
        }

        if (response && response.success) {
          ElMessage.success(this.dialogMode === 'create' ? '新增成功' : '更新成功')
          this.dialogVisible = false
          this.loadOwners()
        } else {
          // 显示后端校验错误
          const errors = response && response.errors
          if (errors) {
            const msg = Object.values(errors).flat().join('；')
            ElMessage.error(msg || '操作失败，请检查输入')
          } else {
            ElMessage.error('操作失败，请稍后重试')
          }
        }
      } catch (error) {
        console.error('提交失败：', error)
        ElMessage.error('操作失败，请稍后重试')
      } finally {
        this.submitting = false
      }
    },

    // 删除业主
    async deleteOwner(id) {
      try {
        await ElMessageBox.confirm('确认删除该业主记录？此操作不可撤销。', '删除确认', {
          confirmButtonText: '确认删除',
          cancelButtonText: '取消',
          type: 'warning'
        })
      } catch (e) {
        return // 用户取消
      }

      try {
        await api.delete(`/api/owners/${id}/`)
        ElMessage.success('删除成功')
        // 如果当前页只有 1 条且不是第 1 页，退回上一页
        if (this.ownerList.length === 1 && this.currentPage > 1) {
          this.currentPage -= 1
        }
        this.loadOwners()
      } catch (error) {
        console.error('删除失败：', error)
        ElMessage.error('删除失败，请稍后重试')
      }
    },

    // 重置表单
    resetForm() {
      this.ownerForm = {
        specific_part: '',
        location_name: '',
        building: '',
        unit: '',
        floor: '',
        room_number: '',
        bind_status: '已绑定',
        ip_address: '',
        unique_id: '',
        plc_ip_address: ''
      }
      if (this.$refs.ownerFormRef) {
        this.$refs.ownerFormRef.clearValidate()
      }
    }
  }
}
</script>

<style scoped>
.search-form {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
