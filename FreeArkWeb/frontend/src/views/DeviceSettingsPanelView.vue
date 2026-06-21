<template>
  <div v-loading="loading" class="device-settings-panel">
    <div v-if="loadError" class="load-error">
      <el-alert type="error" :title="loadError" show-icon />
      <el-button style="margin-top:8px" @click="loadParams">刷新</el-button>
    </div>

    <template v-if="!loading && !loadError">
      <div class="param-groups">
        <div v-for="group in groups" :key="group.sub_type" class="param-group">
          <!-- 分组标题 -->
          <div class="group-header">
            <span class="group-title">{{ group.sub_type_display }}</span>
          </div>

          <el-table :data="group.params" size="small" border>
            <el-table-column label="参数" prop="display_name" width="160" />
            <el-table-column label="当前值" width="140">
              <template #default="{ row }"><span>{{ row.display_value ?? row.current_value ?? '—' }}</span></template>
            </el-table-column>
            <el-table-column label="设置值" width="220">
              <template #default="{ row }">
                <!-- 枚举型参数（开关/模式/精确名）：el-select，不受本次变更影响 -->
                <el-select v-if="row.value_options && row.value_options.length > 0" v-model="inputValues[row.param_name]" size="small" style="width:150px" @change="() => markDirty(row.param_name)">
                  <el-option v-for="opt in row.value_options" :key="opt.raw" :label="opt.label" :value="opt.raw" />
                </el-select>
                <!-- 温度设定参数：步进按钮控件（REQ-FUNC-002） -->
                <div v-else-if="row.param_name.endsWith('_temp_setting')" class="temp-stepper">
                  <el-button
                    size="small"
                    :disabled="inputValues[row.param_name] <= getTempBounds(row.param_name).min"
                    @click="stepTemp(row.param_name, -1)"
                  >－</el-button>
                  <span class="temp-display">{{ formatTempDisplay(inputValues[row.param_name]) }}</span>
                  <el-button
                    size="small"
                    :disabled="inputValues[row.param_name] >= getTempBounds(row.param_name).max"
                    @click="stepTemp(row.param_name, +1)"
                  >＋</el-button>
                </div>
                <!-- 其他数值型参数（若有）：原 el-input-number，保持不变 -->
                <el-input-number v-else v-model="inputValues[row.param_name]" size="small" :min="parseNumJson(row.num_value_json).min" :max="parseNumJson(row.num_value_json).max" :step="parseNumJson(row.num_value_json).step || 1" style="width:150px" @change="() => markDirty(row.param_name)" />
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <!-- 批量提交操作区 -->
      <div class="batch-actions">
        <el-button type="primary" :disabled="submitLoading" @click="handleBatchSubmit">{{ submitLoading ? '提交中...' : '提交' }}</el-button>
        <el-button :disabled="submitLoading" @click="handleCancel">取消</el-button>
        <span v-if="batchStatus === 'success'" class="batch-status success">全部写入成功</span>
        <span v-else-if="batchStatus === 'partial'" class="batch-status warning">部分写入失败，请查看详情</span>
        <span v-else-if="batchStatus === 'failed'" class="batch-status danger">写入失败: {{ batchError }}</span>
        <span v-else-if="batchStatus === 'timeout'" class="batch-status timeout">PLC 写入模块未响应（30s 超时），请检查 freeark-task-scheduler 服务</span>
      </div>

      <!-- 逐项状态展示 -->
      <div v-if="itemStatuses.length > 0" class="item-status-list">
        <div v-for="s in itemStatuses" :key="s.param_name" class="item-status-row">
          <span class="item-param">{{ s.display_name }}</span>
          <el-tag :type="s.success ? 'success' : 'danger'" size="small">{{ s.success ? '成功' : '失败' }}</el-tag>
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

// ─────────────────────────────────────────────────────────────────────────────
// REQ-FUNC-006：温度参数边界映射（以 ℃ 为单位，集中定义便于调整）
// 房间设定温度：16.0 ~ 30.0℃；出风温度设定：10.0 ~ 30.0℃；步长统一 0.5℃
// ─────────────────────────────────────────────────────────────────────────────
const TEMP_BOUNDS_MAP = {
  living_room_temp_setting:       { min: 16.0, max: 30.0, step: 0.5 },
  bedroom_temp_setting:           { min: 16.0, max: 30.0, step: 0.5 },
  study_room_temp_setting:        { min: 16.0, max: 30.0, step: 0.5 },
  children_room_temp_setting:     { min: 16.0, max: 30.0, step: 0.5 },
  fourth_children_room_temp_setting: { min: 16.0, max: 30.0, step: 0.5 },
  supply_air_temp_setting:        { min: 10.0, max: 30.0, step: 0.5 },
}
// 未命中的 _temp_setting 参数安全兜底（禁止手工输入/无界调节）
const TEMP_BOUNDS_DEFAULT = { min: 16.0, max: 30.0, step: 0.5 }

export default {
  name: 'DeviceSettingsPanelView',
  props: {
    specificPart: { type: String, required: true },
  },
  setup(props) {
    const loading = ref(false), loadError = ref(''), groups = ref([])
    const inputValues = ref({}), dirtyFields = ref(new Set()), submitLoading = ref(false)
    const batchStatus = ref(''), batchError = ref(''), itemStatuses = ref([])
    const pendingBatchId = ref(null), timeoutTimer = ref(null)
    const paramDisplayMap = ref({})

    // 获取温度参数边界（REQ-FUNC-006）
    const getTempBounds = (paramName) => TEMP_BOUNDS_MAP[paramName] || TEMP_BOUNDS_DEFAULT

    // 格式化温度展示（保留一位小数，附 ℃）
    const formatTempDisplay = (val) => {
      if (val === null || val === undefined) return '— ℃'
      return `${Number(val).toFixed(1)} ℃`
    }

    // 步进温度值（REQ-FUNC-002/003）：delta = +1 或 -1，步长 0.5℃
    const stepTemp = (paramName, delta) => {
      const bounds = getTempBounds(paramName)
      const current = inputValues.value[paramName]
      if (current === null || current === undefined) return
      // 用整数算术避免浮点精度问题：将 ℃ 值 ×10 运算后再 ÷10
      const currentInt = Math.round(current * 10)
      const stepInt = Math.round(bounds.step * 10)
      const newInt = currentInt + delta * stepInt
      const minInt = Math.round(bounds.min * 10)
      const maxInt = Math.round(bounds.max * 10)
      const clampedInt = Math.max(minInt, Math.min(maxInt, newInt))
      inputValues.value[paramName] = clampedInt / 10
      markDirty(paramName)
    }

    const markDirty = (paramName) => {
      const val = inputValues.value[paramName]
      if (val === undefined || val === null) dirtyFields.value.delete(paramName)
      else dirtyFields.value.add(paramName)
    }

    const loadParams = async () => {
      loading.value = true; loadError.value = ''
      try {
        const data = await api.get(`/api/device-settings/params/${encodeURIComponent(props.specificPart)}/`)
        groups.value = data.groups || []
        groups.value.forEach(g => {
          g.params.forEach(p => {
            paramDisplayMap.value[p.param_name] = p.display_name
            if (!dirtyFields.value.has(p.param_name)) {
              if (p.value_options && p.value_options.length > 0) {
                // 枚举型参数：以字符串形式存入 inputValues
                inputValues.value[p.param_name] = p.current_value !== null && p.current_value !== undefined ? String(p.current_value) : p.value_options[0]?.raw ?? ''
              } else if (p.param_name.endsWith('_temp_setting')) {
                // 温度参数：底层整数 ÷10 转为展示值（℃，一位小数）（REQ-FUNC-002 初始化）
                const rawInt = p.current_value
                inputValues.value[p.param_name] = (rawInt !== null && rawInt !== undefined)
                  ? Math.round(Number(rawInt)) / 10
                  : getTempBounds(p.param_name).min
              } else {
                inputValues.value[p.param_name] = p.current_value
              }
            }
          })
        })
        dirtyFields.value = new Set()
      } catch (e) { loadError.value = '加载参数失败，请刷新重试' }
      finally { loading.value = false }
    }

    const handleBatchSubmit = async () => {
      const allParams = []
      groups.value.forEach(g => { g.params.forEach(p => { allParams.push(p) }) })
      const changedItems = allParams
        .filter(p => dirtyFields.value.has(p.param_name))
        .filter(p => inputValues.value[p.param_name] !== undefined && inputValues.value[p.param_name] !== null)
        .map(p => {
          let newValue
          if (p.param_name.endsWith('_temp_setting')) {
            // REQ-FUNC-004：展示值（℃）×10 取整还原为底层整数字符串
            newValue = String(Math.round(inputValues.value[p.param_name] * 10))
          } else {
            newValue = String(inputValues.value[p.param_name])
          }
          return { param_name: p.param_name, new_value: newValue }
        })
      if (changedItems.length === 0) { ElMessage.warning('没有已修改的参数'); return }
      submitLoading.value = true; batchStatus.value = ''; batchError.value = ''; itemStatuses.value = []; pendingBatchId.value = null
      if (timeoutTimer.value) clearTimeout(timeoutTimer.value)
      try {
        const res = await api.post('/api/device-settings/write/', { specific_part: props.specificPart, items: changedItems })
        pendingBatchId.value = res.batch_request_id
        timeoutTimer.value = setTimeout(() => { if (submitLoading.value) { submitLoading.value = false; batchStatus.value = 'timeout' } }, 30000)
      } catch (e) {
        submitLoading.value = false; batchStatus.value = 'failed'
        const rawMsg = e?.message || ''; const sepIdx = rawMsg.indexOf(' - '); batchError.value = sepIdx !== -1 ? rawMsg.slice(sepIdx + 3) : '未知失败原因，请查看后端日志'
      }
    }

    const handleCancel = () => {
      groups.value.forEach(g => {
        g.params.forEach(p => {
          if (p.value_options && p.value_options.length > 0) {
            inputValues.value[p.param_name] = p.current_value !== null && p.current_value !== undefined ? String(p.current_value) : p.value_options[0]?.raw ?? ''
          } else if (p.param_name.endsWith('_temp_setting')) {
            const rawInt = p.current_value
            inputValues.value[p.param_name] = (rawInt !== null && rawInt !== undefined)
              ? Math.round(Number(rawInt)) / 10
              : getTempBounds(p.param_name).min
          } else {
            inputValues.value[p.param_name] = p.current_value
          }
        })
      })
      batchStatus.value = ''; batchError.value = ''; itemStatuses.value = []; dirtyFields.value = new Set()
    }

    const handleAck = ({ payload }) => {
      try {
        const data = JSON.parse(payload)
        if (!pendingBatchId.value || data.request_id !== pendingBatchId.value) return
        if (timeoutTimer.value) clearTimeout(timeoutTimer.value)
        submitLoading.value = false
        const items = data.items || []
        itemStatuses.value = items.map(item => ({ param_name: item.param_name, display_name: paramDisplayMap.value[item.param_name] || item.param_name, success: item.success, error_message: item.error_message || '' }))
        const allSuccess = items.length > 0 && items.every(i => i.success), anyFail = items.some(i => !i.success)
        if (allSuccess) batchStatus.value = 'success'
        else if (anyFail && items.some(i => i.success)) batchStatus.value = 'partial'
        else { batchStatus.value = 'failed'; batchError.value = items.find(i => !i.success)?.error_message || '写入失败' }
      } catch { /* JSON 解析失败，忽略 */ }
    }

    const ackTopic = `/datacollection/plc/write/ack/${props.specificPart}`
    const { connect, disconnect } = useMqttWebSocket(ackTopic, handleAck)

    onMounted(() => { loadParams(); connect() })
    onUnmounted(() => { disconnect(); if (timeoutTimer.value) clearTimeout(timeoutTimer.value) })

    const parseNumJson = (json) => { if (!json) return { min: undefined, max: undefined, step: 1 }; try { return JSON.parse(json) } catch { return { min: undefined, max: undefined, step: 1 } } }

    return {
      loading, loadError, groups, inputValues, submitLoading, batchStatus, batchError, itemStatuses,
      loadParams, handleBatchSubmit, handleCancel, parseNumJson, markDirty,
      getTempBounds, formatTempDisplay, stepTemp,
    }
  },
}
</script>

<style scoped>
.device-settings-panel { min-height: 200px; }
.param-groups { width: 100%; }
.param-group :deep(.el-table) { border-radius: 0 0 var(--radius-sm) var(--radius-sm); }
.load-error { padding: 16px; }
.batch-actions {
  display: flex; align-items: center; gap: 12px; margin-top: 16px; padding: 12px 0;
  border-top: 1px solid var(--line);
}
.batch-status { font-size: 13px; }
.batch-status.success { color: var(--ok); }
.batch-status.warning { color: var(--warn); }
.batch-status.danger { color: var(--danger); }
.batch-status.timeout { color: var(--warn); }
.item-status-list { margin-top: 8px; padding: 8px 0; }
.item-status-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 13px; }
.item-param { min-width: 160px; color: var(--ink-1); }
.item-err { color: var(--danger); font-size: 12px; }
/* 温度步进控件样式（REQ-FUNC-002） */
.temp-stepper { display: flex; align-items: center; gap: 6px; }
.temp-display {
  display: inline-block; min-width: 72px; text-align: center;
  font-size: 13px; color: var(--ink-0, #222); user-select: none;
}
</style>
