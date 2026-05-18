<template>
  <div v-loading="loading" class="device-settings-panel">
    <div v-if="loadError" class="load-error">
      <el-alert type="error" :title="loadError" show-icon />
      <el-button style="margin-top:8px" @click="loadParams">刷新</el-button>
    </div>

    <el-collapse v-if="!loading && !loadError" v-model="openGroups">
      <el-collapse-item
        v-for="group in groups"
        :key="group.sub_type"
        :name="group.sub_type"
        :title="group.sub_type_display"
      >
        <el-table :data="group.params" size="small" border>
          <el-table-column label="参数" prop="display_name" width="160" />
          <el-table-column label="当前值" width="110">
            <template #default="{ row }">
              <span>{{ currentValues[row.param_name] ?? row.current_value ?? '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="设置值" width="160">
            <template #default="{ row }">
              <template v-if="row.is_writable">
                <el-select
                  v-if="row.attr_value_type === 1"
                  v-model="inputValues[row.param_name]"
                  size="small"
                  style="width:130px"
                >
                  <el-option
                    v-for="opt in parseSelectOptions(row.select_values_json)"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
                <el-input-number
                  v-else
                  v-model="inputValues[row.param_name]"
                  size="small"
                  :min="parseNumJson(row.num_value_json).min"
                  :max="parseNumJson(row.num_value_json).max"
                  :step="parseNumJson(row.num_value_json).step || 1"
                  style="width:130px"
                />
              </template>
              <span v-else class="readonly-hint">只读</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center">
            <template #default="{ row }">
              <template v-if="row.is_writable">
                <el-button
                  v-if="writeStatus[row.param_name] !== 'loading'"
                  type="primary"
                  size="small"
                  @click="handleSubmit(row)"
                >
                  下发
                </el-button>
                <el-button v-else type="primary" size="small" loading disabled>
                  等待中
                </el-button>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="160">
            <template #default="{ row }">
              <el-tag v-if="writeStatus[row.param_name] === 'success'" type="success" size="small">成功</el-tag>
              <el-tag v-else-if="writeStatus[row.param_name] === 'failed'" type="danger" size="small">
                失败: {{ writeErrors[row.param_name] }}
              </el-tag>
              <el-tag v-else-if="writeStatus[row.param_name] === 'timeout'" type="warning" size="small">等待超时</el-tag>
              <span v-else class="status-idle">—</span>
              <el-button
                v-if="writeStatus[row.param_name] === 'failed' || writeStatus[row.param_name] === 'timeout'"
                link
                size="small"
                style="margin-left:4px"
                @click="handleSubmit(row)"
              >
                重试
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>
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
    const currentValues = ref({})
    const writeStatus = ref({})
    const writeErrors = ref({})
    const requestMap = ref({})
    const timers = ref({})

    const loadParams = async () => {
      loading.value = true
      loadError.value = ''
      try {
        const data = await api.get(`/api/device-settings/params/${encodeURIComponent(props.specificPart)}/`)
        groups.value = data.groups || []
        openGroups.value = groups.value.map(g => g.sub_type)
        groups.value.forEach(g => {
          g.params.forEach(p => {
            currentValues.value[p.param_name] = p.current_value
            if (inputValues.value[p.param_name] === undefined) {
              inputValues.value[p.param_name] = p.current_value
            }
          })
        })
      } catch (e) {
        loadError.value = '加载参数失败，请刷新重试'
      } finally {
        loading.value = false
      }
    }

    const handleSubmit = async (row) => {
      const param_name = row.param_name
      const new_value = inputValues.value[param_name]
      if (new_value === undefined || new_value === null) {
        ElMessage.warning('请先填写设置值')
        return
      }
      writeStatus.value[param_name] = 'loading'
      writeErrors.value[param_name] = ''

      if (timers.value[param_name]) {
        clearTimeout(timers.value[param_name])
      }

      try {
        const res = await api.post('/api/device-settings/write/', {
          specific_part: props.specificPart,
          param_name,
          new_value: String(new_value),
        })
        requestMap.value[param_name] = res.request_id
        timers.value[param_name] = setTimeout(() => {
          if (writeStatus.value[param_name] === 'loading') {
            writeStatus.value[param_name] = 'timeout'
          }
        }, 30000)
      } catch (e) {
        writeStatus.value[param_name] = 'failed'
        writeErrors.value[param_name] = e?.response?.data?.error || '下发通道异常'
      }
    }

    const handleAck = ({ payload }) => {
      try {
        const data = JSON.parse(payload)
        const param_name = Object.keys(requestMap.value).find(
          k => requestMap.value[k] === data.request_id
        )
        if (!param_name) return
        if (timers.value[param_name]) {
          clearTimeout(timers.value[param_name])
        }
        if (data.success) {
          writeStatus.value[param_name] = 'success'
          if (data.value !== undefined) {
            currentValues.value[param_name] = data.value
          }
        } else {
          writeStatus.value[param_name] = 'failed'
          writeErrors.value[param_name] = data.error_message || '写入失败'
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
      Object.values(timers.value).forEach(t => clearTimeout(t))
    })

    const parseSelectOptions = (json) => {
      if (!json) return []
      try {
        const parsed = JSON.parse(json)
        if (Array.isArray(parsed)) {
          return parsed.map(item =>
            typeof item === 'object' ? item : { label: String(item), value: item }
          )
        }
        return []
      } catch {
        return []
      }
    }

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
      currentValues,
      writeStatus,
      writeErrors,
      loadParams,
      handleSubmit,
      parseSelectOptions,
      parseNumJson,
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
.readonly-hint {
  color: #909399;
  font-size: 12px;
}
.status-idle {
  color: #c0c4cc;
}
</style>
