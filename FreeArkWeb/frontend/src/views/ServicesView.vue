<template>
  <div class="services-view">
    <div class="sv-page-head">
      <div class="sv-head-accent"></div>
      <div class="sv-head-text">
        <h2 class="sv-head-title">服务管理</h2>
        <p class="sv-head-sub">查看和管理系统后台服务运行状态</p>
      </div>
      <el-button
        v-if="activeTab === 'services'"
        :icon="Refresh"
        :loading="listLoading"
        @click="fetchList"
        style="margin-left: auto; align-self: center;"
      >
        刷新
      </el-button>
    </div>

    <!-- Tab 切换：服务列表 / 心跳中间件配置 (OQ-003 方案 A) -->
    <el-tabs v-model="activeTab" class="services-tabs">
      <!-- ===== Tab 1: 服务列表 ===== -->
      <el-tab-pane label="服务列表" name="services">
        <!-- 服务列表表格 -->
        <el-table
          v-loading="listLoading"
          :data="serviceList"
          stripe
          border
          style="width: 100%; margin-top: 16px;"
        >
          <el-table-column prop="name" label="服务名称" min-width="200" />

          <el-table-column label="运行状态" width="130" align="center">
            <template #default="{ row }">
              <el-tag :type="activeStateTagType(row.active_state)" size="small">
                {{ row.active_state || '未知' }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="自启动" width="110" align="center">
            <template #default="{ row }">
              <el-tag
                :type="row.enabled === 'enabled' ? 'success' : row.enabled === 'disabled' ? 'danger' : 'info'"
                size="small"
              >
                {{ row.enabled || '未知' }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="280" align="center" fixed="right">
            <template #default="{ row }">
              <el-button
                type="success"
                size="small"
                :loading="actionLoading[row.name] === 'start'"
                :disabled="!!actionLoading[row.name]"
                @click="handleAction(row, 'start')"
              >
                启动
              </el-button>
              <el-button
                type="danger"
                size="small"
                :loading="actionLoading[row.name] === 'stop'"
                :disabled="!!actionLoading[row.name]"
                @click="handleAction(row, 'stop')"
              >
                停止
              </el-button>
              <el-button
                type="warning"
                size="small"
                :loading="actionLoading[row.name] === 'restart'"
                :disabled="!!actionLoading[row.name]"
                @click="handleAction(row, 'restart')"
              >
                重启
              </el-button>
              <el-button
                type="primary"
                link
                size="small"
                @click="handleShowDetail(row)"
              >
                详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 服务详情弹窗 -->
        <el-dialog
          v-model="detailVisible"
          :title="`服务详情 — ${detailServiceName}`"
          width="700px"
          destroy-on-close
        >
          <div v-if="detailLoading" class="detail-loading">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>加载中...</span>
          </div>

          <template v-else-if="detailData">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="运行状态">
                <el-tag :type="activeStateTagType(detailData.active_state)" size="small">
                  {{ detailData.active_state || '未知' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="子状态">
                {{ detailData.sub_state || '—' }}
              </el-descriptions-item>
              <el-descriptions-item label="PID">
                {{ detailData.pid !== null && detailData.pid !== undefined ? detailData.pid : '—' }}
              </el-descriptions-item>
              <el-descriptions-item label="内存占用">
                {{ detailData.memory || '—' }}
              </el-descriptions-item>
            </el-descriptions>

            <div class="raw-output-label">systemctl status 原始输出：</div>
            <pre class="raw-output">{{ detailData.raw_output || '（无输出）' }}</pre>
          </template>

          <el-alert
            v-else-if="detailError"
            :title="detailError"
            type="error"
            :closable="false"
            show-icon
          />
        </el-dialog>

        <!-- 操作确认弹窗 -->
        <el-dialog
          v-model="confirmVisible"
          title="确认操作"
          width="400px"
        >
          <p>
            确认对服务
            <strong>{{ confirmServiceName }}</strong>
            执行
            <strong>{{ confirmActionLabel }}</strong>
            操作？
          </p>
          <template #footer>
            <el-button @click="confirmVisible = false">取消</el-button>
            <el-button
              :type="confirmButtonType"
              :loading="confirmExecuting"
              @click="executeConfirmedAction"
            >
              确认
            </el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- ===== Tab 2: 心跳中间件配置 (REQ-FUNC-003, OQ-003 方案 A) ===== -->
      <el-tab-pane label="心跳中间件配置" name="heartbeat-config">
        <div class="hbc-form-wrapper">
          <div v-if="hbcLoading" class="detail-loading">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>加载中...</span>
          </div>

          <el-form
            v-else
            ref="hbcFormRef"
            :model="hbcForm"
            :rules="hbcRules"
            label-width="120px"
            label-position="right"
            class="hbc-form"
          >
            <!-- 协议 -->
            <el-form-item label="协议" prop="protocol">
              <el-select v-model="hbcForm.protocol" style="width: 200px">
                <el-option label="mqtt（TCP）" value="mqtt" />
                <el-option label="wss（WebSocket TLS）" value="wss" />
              </el-select>
            </el-form-item>

            <!-- Host -->
            <el-form-item label="Host" prop="host">
              <el-input v-model="hbcForm.host" placeholder="如 47.117.41.184 或 www.example.com" style="width: 320px" />
            </el-form-item>

            <!-- Port -->
            <el-form-item label="Port" prop="port">
              <el-input-number
                v-model="hbcForm.port"
                :min="1"
                :max="65535"
                controls-position="right"
                style="width: 160px"
              />
            </el-form-item>

            <!-- Path（仅 wss 时显示）-->
            <el-form-item v-if="hbcForm.protocol === 'wss'" label="Path" prop="path">
              <el-input v-model="hbcForm.path" placeholder="如 /mqtt" style="width: 240px" />
            </el-form-item>

            <!-- Username -->
            <el-form-item label="Username" prop="username">
              <el-input v-model="hbcForm.username" style="width: 240px" />
            </el-form-item>

            <!-- Password -->
            <el-form-item label="Password" prop="password">
              <el-input
                v-model="hbcForm.password"
                type="password"
                show-password
                placeholder="留空则不修改"
                style="width: 240px"
              />
            </el-form-item>

            <!-- Topic -->
            <el-form-item label="Topic" prop="topic">
              <el-input v-model="hbcForm.topic" style="width: 400px" />
            </el-form-item>

            <!-- Client ID -->
            <el-form-item label="Client ID" prop="client_id">
              <el-input v-model="hbcForm.client_id" style="width: 280px" />
            </el-form-item>

            <!-- Keepalive -->
            <el-form-item label="Keepalive（秒）" prop="keepalive">
              <el-input-number
                v-model="hbcForm.keepalive"
                :min="1"
                :max="3600"
                controls-position="right"
                style="width: 160px"
              />
            </el-form-item>

            <el-form-item>
              <el-button
                type="primary"
                :loading="hbcSaving"
                @click="handleHbcSave"
              >
                保存并重启服务
              </el-button>
            </el-form-item>
          </el-form>
        </div>

        <!-- 保存确认弹窗 -->
        <el-dialog
          v-model="hbcConfirmVisible"
          title="确认保存配置"
          width="420px"
        >
          <p>保存后将立即重启 <strong>freeark-screen-heartbeat</strong> 服务，重启期间心跳短暂中断（约 30s），确认继续？</p>
          <template #footer>
            <el-button @click="hbcConfirmVisible = false">取消</el-button>
            <el-button type="primary" :loading="hbcSaving" @click="executeHbcSave">确认</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
import { ref, reactive, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Loading } from '@element-plus/icons-vue'
import api from '@/utils/api.js'

export default {
  name: 'ServicesView',

  components: { Refresh, Loading },

  setup() {
    // ================================================================
    // Tab 状态
    // ================================================================
    const activeTab = ref('services')

    // ================================================================
    // Tab 1: 服务列表
    // ================================================================
    const serviceList = ref([])
    const listLoading = ref(false)

    // actionLoading: { [serviceName]: 'start'|'stop'|'restart'|null }
    const actionLoading = reactive({})

    // --- 详情弹窗状态 ---
    const detailVisible = ref(false)
    const detailServiceName = ref('')
    const detailData = ref(null)
    const detailLoading = ref(false)
    const detailError = ref('')

    // --- 确认弹窗状态 ---
    const confirmVisible = ref(false)
    const confirmServiceName = ref('')
    const confirmAction = ref('')
    const confirmExecuting = ref(false)

    const ACTION_LABELS = { start: '启动', stop: '停止', restart: '重启' }
    const ACTION_BUTTON_TYPES = { start: 'success', stop: 'danger', restart: 'warning' }

    const confirmActionLabel = ref('')
    const confirmButtonType = ref('primary')

    // --- 辅助函数 ---
    const activeStateTagType = (state) => {
      if (state === 'active') return 'success'
      if (state === 'failed') return 'danger'
      if (state === 'inactive') return 'warning'
      return 'info'
    }

    // --- API：获取服务列表 ---
    const fetchList = async () => {
      listLoading.value = true
      try {
        const resp = await api.get('/api/services/list/')
        if (resp && resp.success) {
          serviceList.value = resp.data || []
        } else {
          ElMessage.error(resp?.error || '获取服务列表失败')
        }
      } catch (err) {
        ElMessage.error('获取服务列表失败：' + (err.message || '网络错误'))
      } finally {
        listLoading.value = false
      }
    }

    // --- 操作：弹出确认框 ---
    const handleAction = (row, action) => {
      confirmServiceName.value = row.name
      confirmAction.value = action
      confirmActionLabel.value = ACTION_LABELS[action] || action
      confirmButtonType.value = ACTION_BUTTON_TYPES[action] || 'primary'
      confirmVisible.value = true
    }

    // --- 操作：确认后执行 ---
    const executeConfirmedAction = async () => {
      const name = confirmServiceName.value
      const action = confirmAction.value
      confirmExecuting.value = true
      actionLoading[name] = action

      try {
        const resp = await api.post(`/api/services/${encodeURIComponent(name)}/action/`, { action })
        if (resp && resp.success) {
          ElMessage.success(resp.message || `${name} ${action} 成功`)
          // 更新列表中该服务的 active_state
          const item = serviceList.value.find(s => s.name === name)
          if (item && resp.new_status) {
            item.active_state = resp.new_status
            item.is_active = resp.new_status === 'active'
          }
        } else {
          ElMessage.error(resp?.error || `${name} ${action} 失败`)
        }
      } catch (err) {
        ElMessage.error(`执行失败：${err.message || '网络错误'}`)
      } finally {
        confirmExecuting.value = false
        confirmVisible.value = false
        actionLoading[name] = null
      }
    }

    // --- 详情：打开弹窗并加载 ---
    const handleShowDetail = async (row) => {
      detailServiceName.value = row.name
      detailData.value = null
      detailError.value = ''
      detailLoading.value = true
      detailVisible.value = true

      try {
        const resp = await api.get(`/api/services/${encodeURIComponent(row.name)}/detail/`)
        if (resp && resp.success) {
          detailData.value = resp.detail || {}
        } else {
          detailError.value = resp?.error || '获取服务详情失败'
        }
      } catch (err) {
        detailError.value = '获取服务详情失败：' + (err.message || '网络错误')
      } finally {
        detailLoading.value = false
      }
    }

    // ================================================================
    // Tab 2: 心跳中间件配置 (REQ-FUNC-003, OQ-003 方案 A)
    // ================================================================
    const hbcLoading = ref(false)
    const hbcSaving = ref(false)
    const hbcConfirmVisible = ref(false)
    const hbcFormRef = ref(null)

    const hbcForm = reactive({
      protocol: 'mqtt',
      host: '',
      port: 11883,
      path: '/mqtt',
      username: '',
      password: '',
      topic: '',
      client_id: '',
      keepalive: 60,
    })

    const hbcRules = {
      protocol: [{ required: true, message: '请选择协议', trigger: 'change' }],
      host: [{ required: true, message: 'Host 不能为空', trigger: 'blur' }],
      port: [
        { required: true, message: 'Port 不能为空', trigger: 'blur' },
        {
          validator: (rule, value, callback) => {
            if (!Number.isInteger(value) || value < 1 || value > 65535) {
              callback(new Error('端口号范围：1-65535'))
            } else {
              callback()
            }
          },
          trigger: 'blur',
        },
      ],
      topic: [{ required: true, message: 'Topic 不能为空', trigger: 'blur' }],
    }

    // 协议切换联动：port 默认值跟随协议切换（仅当端口还是典型默认值时自动切换）
    watch(() => hbcForm.protocol, (newProto) => {
      if (newProto === 'wss' && hbcForm.port === 1883) {
        hbcForm.port = 8084
      } else if (newProto === 'mqtt' && hbcForm.port === 8084) {
        hbcForm.port = 1883
      }
    })

    // 加载当前配置
    const fetchHbcConfig = async () => {
      hbcLoading.value = true
      try {
        const resp = await api.get('/api/heartbeat-broker-config/')
        if (resp && resp.success && resp.data) {
          const d = resp.data
          hbcForm.protocol  = d.protocol  || 'mqtt'
          hbcForm.host      = d.host      || ''
          hbcForm.port      = d.port      || 11883
          hbcForm.path      = d.path      || '/mqtt'
          hbcForm.username  = d.username  || ''
          hbcForm.password  = ''   // OQ-004: GET 返回空，前端以 placeholder 提示
          hbcForm.topic     = d.topic     || ''
          hbcForm.client_id = d.client_id || ''
          hbcForm.keepalive = d.keepalive || 60
        } else {
          ElMessage.warning('获取心跳 Broker 配置失败，将显示默认值')
        }
      } catch (err) {
        ElMessage.error('获取心跳 Broker 配置失败：' + (err.message || '网络错误'))
      } finally {
        hbcLoading.value = false
      }
    }

    // 点击「保存并重启服务」—— 先做前端校验，再弹确认框
    const handleHbcSave = async () => {
      if (!hbcFormRef.value) return
      try {
        await hbcFormRef.value.validate()
        hbcConfirmVisible.value = true
      } catch {
        // 校验失败，el-form 会自动显示错误提示
      }
    }

    // 确认弹窗「确认」—— 提交 PUT
    const executeHbcSave = async () => {
      hbcSaving.value = true
      try {
        const payload = {
          protocol:  hbcForm.protocol,
          host:      hbcForm.host,
          port:      hbcForm.port,
          path:      hbcForm.path,
          username:  hbcForm.username,
          password:  hbcForm.password,   // 空字符串 = 后端保留原值 (OQ-004)
          topic:     hbcForm.topic,
          client_id: hbcForm.client_id,
          keepalive: hbcForm.keepalive,
        }
        const resp = await api.put('/api/heartbeat-broker-config/update/', payload)
        if (resp && resp.success) {
          ElMessage.success(resp.message || '配置已保存，服务重启中')
          hbcForm.password = ''  // 保存成功后清空密码输入框
        } else {
          ElMessage.error(resp?.error || '保存失败，请手动重启服务')
        }
      } catch (err) {
        ElMessage.error('保存失败：' + (err.message || '网络错误'))
      } finally {
        hbcSaving.value = false
        hbcConfirmVisible.value = false
      }
    }

    // 切换到心跳配置 Tab 时自动加载
    watch(activeTab, (tab) => {
      if (tab === 'heartbeat-config' && !hbcForm.host) {
        fetchHbcConfig()
      }
    })

    onMounted(() => {
      fetchList()
    })

    return {
      // Tab
      activeTab,
      // Tab 1
      serviceList,
      listLoading,
      actionLoading,
      detailVisible,
      detailServiceName,
      detailData,
      detailLoading,
      detailError,
      confirmVisible,
      confirmServiceName,
      confirmActionLabel,
      confirmButtonType,
      confirmExecuting,
      Refresh,
      Loading,
      activeStateTagType,
      fetchList,
      handleAction,
      executeConfirmedAction,
      handleShowDetail,
      // Tab 2
      hbcLoading,
      hbcSaving,
      hbcConfirmVisible,
      hbcFormRef,
      hbcForm,
      hbcRules,
      handleHbcSave,
      executeHbcSave,
    }
  },
}
</script>

<style scoped>
.services-view {
  padding: 0;
}

/* 页面标题区 */
.sv-page-head {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--line);
}

.sv-head-accent {
  width: 3px;
  min-height: 38px;
  border-radius: 2px;
  background: linear-gradient(180deg, var(--violet), var(--acc));
  flex-shrink: 0;
  margin-top: 2px;
  box-shadow: 0 0 8px rgba(167,139,250,0.45);
}

.sv-head-title {
  margin: 0 0 4px 0;
  color: var(--ink-0);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  line-height: 1.2;
}

.sv-head-sub {
  margin: 0;
  color: var(--ink-2);
  font-size: var(--font-size-sm);
}

.services-tabs {
  margin-top: 0;
}

.detail-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ink-2);
  padding: 20px 0;
  justify-content: center;
}

.raw-output-label {
  margin-top: 16px;
  margin-bottom: 6px;
  font-size: 13px;
  color: var(--ink-2);
  font-weight: 500;
}

.raw-output {
  background: rgba(5,10,20,0.8);
  color: #c7d4ea;
  padding: 12px 16px;
  border-radius: var(--radius-base);
  border: 1px solid var(--line);
  font-size: 12px;
  font-family: var(--font-family-mono);
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 320px;
  overflow-y: auto;
}

/* 心跳配置表单 */
.hbc-form-wrapper {
  margin-top: 16px;
}

.hbc-form {
  max-width: 600px;
}
</style>
