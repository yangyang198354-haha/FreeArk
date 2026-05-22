<template>
  <!--
    REQ-FUNC-034 / MOD-FE-05: 设备参数设置独立路由页面
    取代原 DeviceManagementDeviceListView 中的 el-dialog 弹窗
    specific_part 通过路由 query param 传入
  -->
  <div class="device-management-settings">
    <!-- 页面头部 -->
    <div class="page-header">
      <el-button :icon="ArrowLeft" size="small" @click="goBack">返回</el-button>
      <div class="page-title-group">
        <h2>参数设置</h2>
        <p class="page-subtitle" v-if="specificPart">专有部分：{{ specificPart }}</p>
      </div>
    </div>

    <!-- specific_part 缺失时提示 -->
    <el-alert
      v-if="!specificPart"
      title="缺少设备参数"
      description="URL 中未携带 specific_part 参数，无法加载设置页面。请从设备列表重新进入。"
      type="warning"
      show-icon
      :closable="false"
    />

    <!-- 参数设置面板（REQ-FUNC-034 / AC-020-02/04/05） -->
    <DeviceSettingsPanelView
      v-if="specificPart"
      :specific-part="specificPart"
    />
  </div>
</template>

<script>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import DeviceSettingsPanelView from '@/views/DeviceSettingsPanelView.vue'

export default {
  name: 'DeviceManagementSettingsView',

  components: { ArrowLeft, DeviceSettingsPanelView },

  setup() {
    const route = useRoute()
    const router = useRouter()

    // REQ-FUNC-034: specific_part 从路由 query param 取得
    const specificPart = computed(() => route.query.specific_part || '')

    // AC-020-03: 返回设备列表
    function goBack() {
      router.push('/device-management/device-list')
    }

    return {
      specificPart,
      goBack,
      ArrowLeft,
    }
  },
}
</script>

<style scoped>
/* REQ-NFN-008: 遵循全站科技深蓝主题，不引入独立背景色或弹窗阴影 */
.device-management-settings {
  padding: 0;
}

.page-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 20px;
}

.page-title-group {
  display: flex;
  flex-direction: column;
}

.page-header h2 {
  margin: 0;
  font-weight: 600;
  color: #303133;
  font-size: 20px;
}

/* REQ-FUNC-030 / AC-020-02: 副标题显示 specific_part */
.page-subtitle {
  margin: 5px 0 0 0;
  color: #909399;
  font-size: 13px;
}
</style>
