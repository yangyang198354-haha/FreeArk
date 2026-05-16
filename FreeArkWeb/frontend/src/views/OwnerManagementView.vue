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
        <div style="margin-bottom: 12px; display: flex; gap: 8px; align-items: center;">
          <el-button v-if="isAdmin" type="primary" @click="openCreateDialog">新增业主</el-button>
          <!-- US-04: 批量同步全部设备信息 -->
          <el-button
            type="warning"
            :loading="ownerBatchRunning"
            @click="handleOwnerBatchSync"
          >
            同步全部设备信息（约{{ ownerTotalCount }}户）
          </el-button>
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
          <!-- US-02: 房间数量列 -->
          <el-table-column prop="room_count" label="房间数量" width="90" align="center">
            <template #default="{ row }">
              {{ row.room_count ?? 0 }}
            </template>
          </el-table-column>
          <!-- US-03: 查看明细 + 编辑/删除 -->
          <el-table-column label="操作" width="230" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="info" @click="openDetailDrawer(row)">查看明细</el-button>
              <el-button v-if="isAdmin" size="small" type="primary" @click="openEditDialog(row)" style="margin-left: 4px;">编辑</el-button>
              <el-button v-if="isAdmin" size="small" type="danger" @click="deleteOwner(row.id)" style="margin-left: 4px;">删除</el-button>
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

    <!-- US-03: 查看明细抽屉 -->
    <el-drawer
      v-model="detailDrawerVisible"
      title="设备树明细"
      direction="rtl"
      size="700px"
      :destroy-on-close="true"
    >
      <div v-if="detailLoading" style="text-align: center; padding: 40px;">
        <el-text>加载中...</el-text>
      </div>
      <div v-else-if="!detailData" style="text-align: center; padding: 40px; color: #909399;">
        暂无设备树数据（尚未同步）
      </div>
      <div v-else>
        <div style="margin-bottom: 12px;">
          <el-text type="info">专有部分：</el-text>
          <el-text>{{ detailData.specific_part }}</el-text>
          &nbsp;&nbsp;
          <el-text type="info">坐落：</el-text>
          <el-text>{{ detailData.location_name }}</el-text>
        </div>
        <div v-if="detailData.floors && detailData.floors.length === 0" style="color: #909399; padding: 20px 0;">
          暂无楼层数据（尚未同步设备树）
        </div>
        <el-collapse v-else>
          <el-collapse-item
            v-for="floor in detailData.floors"
            :key="floor.floor_no"
            :title="`${floor.floor_name}（${floor.rooms ? floor.rooms.length : 0} 个房间）`"
            :name="floor.floor_no"
          >
            <div v-if="!floor.rooms || floor.rooms.length === 0" style="color: #909399; padding: 8px 0;">
              该楼层暂无房间
            </div>
            <div v-for="room in floor.rooms" :key="room.ori_room_name" style="margin-bottom: 16px;">
              <div style="font-weight: 600; margin-bottom: 6px;">
                {{ room.room_name }}
                <el-tag size="small" style="margin-left: 6px;">{{ room.devices ? room.devices.length : 0 }} 台设备</el-tag>
              </div>
              <el-table
                v-if="room.devices && room.devices.length > 0"
                :data="room.devices"
                size="small"
                border
                stripe
              >
                <el-table-column prop="device_name" label="设备名" />
                <el-table-column prop="device_sn" label="SN" width="80" align="center" />
                <el-table-column prop="product_code" label="产品编码" width="100" align="center" />
                <el-table-column label="类型" width="70" align="center">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.system_flag === 2 ? 'primary' : 'info'">
                      {{ row.system_flag === 2 ? '主机' : '子机' }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
              <div v-else style="color: #909399; font-size: 13px; padding: 4px 0;">
                该房间暂无设备
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
      <template #footer>
        <el-button @click="detailDrawerVisible = false">关闭</el-button>
      </template>
    </el-drawer>

    <!-- US-04: 批量同步进度弹窗 -->
    <el-dialog
      v-model="ownerBatchDialogVisible"
      title="批量同步设备信息"
      width="640px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="!ownerBatchRunning"
    >
      <div>
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px;">
          <el-tag size="large" :type="ownerBatchRunning ? 'warning' : 'success'">
            {{ ownerBatchStatusLabel }}
          </el-tag>
          <span>
            {{ ownerBatchProgress.processed }} / {{ ownerBatchProgress.total }}
            （成功 {{ ownerBatchProgress.success }} · 失败 {{ ownerBatchProgress.failed }}）
          </span>
        </div>
        <el-progress
          :percentage="ownerBatchPercentage"
          :status="ownerBatchRunning ? '' : (ownerBatchProgress.failed > 0 ? 'exception' : 'success')"
          style="margin: 12px 0"
        />
        <div v-if="ownerBatchProgress.errors && ownerBatchProgress.errors.length > 0">
          <div style="font-weight: 600; margin-bottom: 6px;">
            失败记录 ({{ ownerBatchProgress.errors.length }})
          </div>
          <el-table
            :data="ownerBatchProgress.errors"
            size="small"
            border
            stripe
            max-height="240"
          >
            <el-table-column prop="specific_part" label="专有部分" width="160" />
            <el-table-column prop="message" label="错误信息" />
          </el-table>
        </div>
      </div>
      <template #footer>
        <el-button :disabled="ownerBatchRunning" @click="ownerBatchDialogVisible = false">
          {{ ownerBatchRunning ? '同步中...' : '关闭' }}
        </el-button>
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
      userRole: 'user',

      // US-03: 查看明细抽屉
      detailDrawerVisible: false,
      detailLoading: false,
      detailData: null,

      // US-04: 批量同步状态
      ownerTotalCount: 0,
      ownerBatchTaskId: '',
      ownerBatchDialogVisible: false,
      ownerBatchRunning: false,
      ownerBatchPollTimer: null,
      ownerBatchProgress: {
        total: 0,
        processed: 0,
        success: 0,
        failed: 0,
        status: 'pending',
        errors: [],
      },
    }
  },

  computed: {
    isAdmin() {
      return this.userRole === 'admin'
    },
    // US-04
    ownerBatchStatusLabel() {
      const s = this.ownerBatchProgress.status
      if (s === 'pending') return '排队中'
      if (s === 'running') return '同步中'
      if (s === 'finished') return '已完成'
      if (s === 'failed') return '已失败'
      return s
    },
    ownerBatchPercentage() {
      if (!this.ownerBatchProgress.total) return 0
      return Math.floor((this.ownerBatchProgress.processed / this.ownerBatchProgress.total) * 100)
    },
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
    this.loadOwnerTotalCount()  // US-04: 获取总户数用于按钮文案
  },

  beforeUnmount() {
    this.stopOwnerBatchPolling()
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
    },

    // -----------------------------------------------------------------------
    // US-03: 查看明细抽屉
    // -----------------------------------------------------------------------
    async openDetailDrawer(row) {
      this.detailDrawerVisible = true
      this.detailLoading = true
      this.detailData = null
      try {
        const resp = await api.get(`/api/owners/${row.id}/device-tree/`)
        if (resp && resp.success) {
          this.detailData = resp.data
        } else {
          this.detailData = null
        }
      } catch (e) {
        ElMessage.error('获取设备树明细失败，请稍后重试')
        this.detailData = null
      } finally {
        this.detailLoading = false
      }
    },

    // -----------------------------------------------------------------------
    // US-04: 批量同步全部设备信息
    // -----------------------------------------------------------------------

    // 获取总户数（用于按钮文案显示，不传 specific_parts → 后端全量回退）
    async loadOwnerTotalCount() {
      try {
        const resp = await api.get('/api/owners/?page=1&page_size=1')
        if (resp && typeof resp.total === 'number') {
          this.ownerTotalCount = resp.total
        }
      } catch (e) {
        // 静默失败，按钮文案保持默认
      }
    },

    stopOwnerBatchPolling() {
      if (this.ownerBatchPollTimer) {
        clearInterval(this.ownerBatchPollTimer)
        this.ownerBatchPollTimer = null
      }
    },

    async pollOwnerBatchStatus() {
      if (!this.ownerBatchTaskId) return
      try {
        const resp = await api.get(
          `/api/device-management/screen-device-tree/batch-sync/${encodeURIComponent(this.ownerBatchTaskId)}/`
        )
        this.ownerBatchProgress.total = resp.total ?? this.ownerBatchProgress.total
        this.ownerBatchProgress.processed = resp.processed ?? 0
        this.ownerBatchProgress.success = resp.success ?? 0
        this.ownerBatchProgress.failed = resp.failed ?? 0
        this.ownerBatchProgress.status = resp.status || 'running'
        this.ownerBatchProgress.errors = Array.isArray(resp.errors) ? resp.errors : []
        if (resp.status === 'finished' || resp.status === 'failed') {
          this.ownerBatchRunning = false
          this.stopOwnerBatchPolling()
          ElMessage({
            type: this.ownerBatchProgress.failed > 0 ? 'warning' : 'success',
            message: `批量同步完成：成功 ${this.ownerBatchProgress.success} / 失败 ${this.ownerBatchProgress.failed}`,
            duration: 4000,
          })
          // Q-04-4: 自动刷新列表
          this.loadOwners()
        }
      } catch (err) {
        console.warn('poll owner batch status failed', err)
      }
    },

    async handleOwnerBatchSync() {
      // Q-04-3: 任务进行中再次点击 → 恢复进度弹窗，不重复发起
      if (this.ownerBatchRunning && this.ownerBatchTaskId) {
        this.ownerBatchDialogVisible = true
        return
      }

      // Q-04-2: 二次确认弹窗
      const minutes = Math.max(1, Math.ceil(this.ownerTotalCount / 60))
      try {
        await ElMessageBox.confirm(
          `将同步全部约 ${this.ownerTotalCount} 户的设备信息，预计耗时 ${minutes} 分钟，确认？`,
          '批量同步',
          { confirmButtonText: '开始同步', cancelButtonText: '取消', type: 'warning' }
        )
      } catch {
        return
      }

      // 发起批量同步（不传 specific_parts，后端自动全量回退）
      try {
        this.ownerBatchRunning = true
        this.ownerBatchProgress.total = this.ownerTotalCount
        this.ownerBatchProgress.processed = 0
        this.ownerBatchProgress.success = 0
        this.ownerBatchProgress.failed = 0
        this.ownerBatchProgress.status = 'pending'
        this.ownerBatchProgress.errors = []
        this.ownerBatchDialogVisible = true

        const resp = await api.post('/api/device-management/screen-device-tree/batch-sync/', {})
        this.ownerBatchTaskId = resp.task_id
        this.ownerBatchProgress.total = resp.total ?? this.ownerTotalCount

        // 轮询进度（每 2 秒）
        this.stopOwnerBatchPolling()
        this.ownerBatchPollTimer = setInterval(() => this.pollOwnerBatchStatus(), 2000)
        this.pollOwnerBatchStatus()
      } catch (err) {
        this.ownerBatchRunning = false
        ElMessage.error(`启动批量同步失败：${err?.message || err}`)
      }
    },
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
