<template>
  <div v-loading="loading" class="device-settings-panel">
    <div v-if="loadError" class="load-error">
      <el-alert type="error" :title="loadError" show-icon />
      <el-button style="margin-top:8px" @click="loadParams">刷新</el-button>
    </div>

    <template v-if="!loading && !loadError">
      <el-collapse v-model="openGroups">
        <el-collapse-item
          v-for="group in groups"
          :key="group.sub_type"
          :name="group.sub_type"
          :title="group.sub_type_display"
        >
          <el-table :data="group.params" size="small" border>
            <el-table-column label="参数" prop="display_name" width="160" />
            <el-table-column label="当前值" width="140">
              <template #default="{ row }">
                <span>{{ row.display_value ?? row.current_value ?? '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="设置值" width="180">
              <template #default="{ row }">
                <el-select
                  v-if="row.value_options && row.value_options.length > 0"
                  v-model="inputValues[row.param_name]"
                  size="small"
                  style="width:150px"
                  @change="() => markDirty(row.param_name)"
                >
                  <el-option
                    v-for="opt in row.value_options"
                    :key="opt.raw"
                    :label="opt.label"
                    :value="opt.raw"
                  />
                </el-select>
                <el-input-number
                  v-else
                  v-model="inputValues[row.param_name]"
                  size="small"
                  :min="parseNumJson(row.num_value_json).min"
                  :max="parseNumJson(row.num_value_json).max"
                  :step="parseNumJson(row.num_value_json).step || 1"
                  style="width:150px"
                  @change="() => markDirty(row.param_name)"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>

      <!-- 批量提交操作区 -->
      <div class="batch-actions">
        <el-button type="primary" :disabled="submitLoading" @click="handleBatchSubmit">
          {{ submitLoading ? '提交中...' : '提交' }}
        </el-button>
        <el-button :disabled="submitLoading" @click="handleCancel">取消</el-button>
        <span v-if="batchStatus === 'success'" class="batch-status success">全部写入成功</span>
        <span v-else-if="batchStatus === 'partial'" class="batch-status warning">部分写入失败，请查看详情</span>
        <span v-else-if="batchStatus === 'failed'" class="batch-status danger">写入失败: {{ batchError }}</span>
        <span v-else-if="batchStatus === 'timeout'" class="batch-status timeout">
          PLC 写入模块未响应（30s 超时），请检查 freeark-task-scheduler 服务
        </span>
      </div>

      <!-- 逐项状态展示（有结果时显示） -->
      <div v-if="itemStatuses.length > 0" class="item-status-list">
        <div v-for="s in itemStatuses" :key="s.param_name" class="item-status-row">
          <span class="item-param">{{ s.display_name }}</span>
          <el-tag :type="s.success ? 'success' : 'danger'" size="small">
            {{ s.success ? '成功' : '失败' }}
          </el-tag>
          <span v-if="!s.success" class="item-err">{{ s.error_message }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/utils/api.js'
import { useMqttWebSocket } from '@/composables/useMqttWebSocket.js'

export default {
  name: 'DeviceSettingsPanelView',

  props: {
    specificPart: {
      type: String,
      required: true,
    },
  },

  setup(props) {
    const loading = ref(false)
    const loadError = ref('')
    const groups = ref([])
    const openGroups = ref([])

    const inputValues = ref({})
    const dirtyFields = ref(new Set())  // v0.5.0: 脏值追踪 Set（REQ-FUNC-004, ADR-10）
    const submitLoading = ref(false)
    const batchStatus = ref('')
    const batchError = ref('')
    const itemStatuses = ref([])
    const pendingBatchId = ref(null)
    const timeoutTimer = ref(null)

    // 参数名 -> display_name 映射，用于逐项状态展示
    const paramDisplayMap = ref({})

    // v0.5.0: 标记参数为脏（用户已修改，REQ-FUNC-004, ADR-10）
    // FR-001 fix: el-input-number 清空后 value=undefined，不应标记为有效修改；
    //   undefined/null → 从 dirtyFields 移除（清空等同于撤销修改）
    //   有效值 → 正常 add
    const markDirty = (paramName) => {
      const val = inputValues.value[paramName]
      if (val === undefined || val === null) {
        dirtyFields.value.delete(paramName)
      } else {
        dirtyFields.value.add(paramName)
      }
    }

    const loadParams = async () => {
      loading.value = true
      loadError.value = ''
      try {
        const data = await api.get(`/api/device-settings/params/${encodeURIComponent(props.specificPart)}/`)
        groups.value = data.groups || []
        openGroups.value = groups.value.map(g => g.sub_type)
        groups.value.forEach(g => {
          g.params.forEach(p => {
            paramDisplayMap.value[p.param_name] = p.display_name
            // v0.5.0 GROUP_B Minor finding 修正：
            //   原逻辑 `if (inputValues[p.param_name] === undefined)` 仅初始化一次，
            //   重新 loadParams 时不会刷新已有值，与 dirtyFields 语义冲突。
            //   修正：仅在该参数无脏修改时才用服务端最新值刷新（有 dirty 说明用户正在编辑，保留）。
            //   loadParams 完成后统一清空 dirtyFields，恢复干净状态。
            if (!dirtyFields.value.has(p.param_name)) {
              // 枚举型用 raw 字符串，数值型用当前值（number）
              if (p.value_options && p.value_options.length > 0) {
                inputValues.value[p.param_name] = p.current_value !== null && p.current_value !== undefined
                  ? String(p.current_value)
                  : p.value_options[0]?.raw ?? ''
              } else {
                inputValues.value[p.param_name] = p.current_value
              }
            }
          })
        })
        dirtyFields.value = new Set()  // 重新加载完成后清空脏状态（REQ-FUNC-004）
      } catch (e) {
        loadError.value = '加载参数失败，请刷新重试'
      } finally {
        loading.value = false
      }
    }

    const handleBatchSubmit = async () => {
      const allParams = []
      groups.value.forEach(g => {
        g.params.forEach(p => {
          allParams.push(p)
        })
      })

      // v0.5.0: 仅提交用户实际修改过的字段（REQ-FUNC-004, ADR-10）
      // FR-001 fix: 防御性过滤 undefined/null（markDirty 已在上游处理，此处为双重保护）
      const changedItems = allParams
        .filter(p => dirtyFields.value.has(p.param_name))
        .filter(p => inputValues.value[p.param_name] !== undefined
                  && inputValues.value[p.param_name] !== null)
        .map(p => ({
          param_name: p.param_name,
          new_value: String(inputValues.value[p.param_name]),
        }))

      if (changedItems.length === 0) {
        ElMessage.warning('没有已修改的参数')
        return
      }

      submitLoading.value = true
      batchStatus.value = ''
      batchError.value = ''
      itemStatuses.value = []
      pendingBatchId.value = null

      if (timeoutTimer.value) {
        clearTimeout(timeoutTimer.value)
      }

      try {
        const res = await api.post('/api/device-settings/write/', {
          specific_part: props.specificPart,
          items: changedItems,
        })
        pendingBatchId.value = res.batch_request_id

        // D3：30s 超时计时器
        timeoutTimer.value = setTimeout(() => {
          if (submitLoading.value) {
            submitLoading.value = false
            batchStatus.value = 'timeout'
          }
        }, 30000)
      } catch (e) {
        submitLoading.value = false
        batchStatus.value = 'failed'
        // api.js 使用原生 fetch，抛出普通 Error 对象（无 .response.data 结构）
        // Error.message 格式: "API请求失败: <status> <statusText> - <backend error>"
        // 提取 " - " 之后的后端错误描述；若无则降级到通用提示
        const rawMsg = e?.message || ''
        const sepIdx = rawMsg.indexOf(' - ')
        batchError.value = sepIdx !== -1 ? rawMsg.slice(sepIdx + 3) : '未知失败原因，请查看后端日志'
      }
    }

    const handleCancel = () => {
      // 重置 inputValues 为当前服务端值
      groups.value.forEach(g => {
        g.params.forEach(p => {
          if (p.value_options && p.value_options.length > 0) {
            inputValues.value[p.param_name] = p.current_value !== null && p.current_value !== undefined
              ? String(p.current_value)
              : p.value_options[0]?.raw ?? ''
          } else {
            inputValues.value[p.param_name] = p.current_value
          }
        })
      })
      batchStatus.value = ''
      batchError.value = ''
      itemStatuses.value = []
      dirtyFields.value = new Set()  // v0.5.0: 取消时清空脏状态（REQ-FUNC-004）
    }

    const handleAck = ({ payload }) => {
      try {
        const data = JSON.parse(payload)
        if (!pendingBatchId.value || data.request_id !== pendingBatchId.value) return

        if (timeoutTimer.value) {
          clearTimeout(timeoutTimer.value)
        }
        submitLoading.value = false

        const items = data.items || []
        itemStatuses.value = items.map(item => ({
          param_name: item.param_name,
          display_name: paramDisplayMap.value[item.param_name] || item.param_name,
          success: item.success,
          error_message: item.error_message || '',
        }))

        const allSuccess = items.length > 0 && items.every(i => i.success)
        const anyFail = items.some(i => !i.success)

        if (allSuccess) {
          batchStatus.value = 'success'
        } else if (anyFail && items.some(i => i.success)) {
          batchStatus.value = 'partial'
        } else {
          batchStatus.value = 'failed'
          batchError.value = items.find(i => !i.success)?.error_message || '写入失败'
        }
      } catch {
        // JSON 解析失败，忽略
      }
    }

    const ackTopic = `/datacollection/plc/write/ack/${props.specificPart}`
    const { connect, disconnect } = useMqttWebSocket(ackTopic, handleAck)

    onMounted(() => {
      loadParams()
      connect()
    })

    onUnmounted(() => {
      disconnect()
      if (timeoutTimer.value) clearTimeout(timeoutTimer.value)
    })

    const parseNumJson = (json) => {
      if (!json) return { min: undefined, max: undefined, step: 1 }
      try {
        return JSON.parse(json)
      } catch {
        return { min: undefined, max: undefined, step: 1 }
      }
    }

    return {
      loading,
      loadError,
      groups,
      openGroups,
      inputValues,
      submitLoading,
      batchStatus,
      batchError,
      itemStatuses,
      loadParams,
      handleBatchSubmit,
      handleCancel,
      parseNumJson,
      markDirty,  // v0.5.0: 暴露给模板的脏值标记函数（REQ-FUNC-004）
    }
  },
}
</script>

<style scoped>
.device-settings-panel {
  min-height: 200px;
}
.load-error {
  padding: 16px;
}
.batch-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding: 12px 0;
  border-top: 1px solid #ebeef5;
}
.batch-status {
  font-size: 13px;
}
.batch-status.success {
  color: #67c23a;
}
.batch-status.warning {
  color: #e6a23c;
}
.batch-status.danger {
  color: #f56c6c;
}
.batch-status.timeout {
  color: #e6a23c;
}
.item-status-list {
  margin-top: 8px;
  padding: 8px 0;
}
.item-status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 13px;
}
.item-param {
  min-width: 160px;
  color: #606266;
}
.item-err {
  color: #f56c6c;
  font-size: 12px;
}
</style>
