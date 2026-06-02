<template>
  <div class="device-management-settings">
    <div class="page-head">
      <el-button :icon="ArrowLeft" size="small" @click="goBack" style="flex-shrink:0;">返回</el-button>
      <div class="ph-accent"></div>
      <div class="ph-text">
        <h2 class="ph-title">参数设置</h2>
        <p class="ph-sub" v-if="specificPart">专有部分：{{ specificPart }}</p>
      </div>
    </div>

    <el-alert
      v-if="!specificPart"
      title="缺少设备参数"
      description="URL 中未携带 specific_part 参数，无法加载设置页面。请从设备列表重新进入。"
      type="warning"
      show-icon
      :closable="false"
    />

    <DeviceSettingsPanelView v-if="specificPart" :specific-part="specificPart" />
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
    const route = useRoute(), router = useRouter()
    const specificPart = computed(() => route.query.specific_part || '')
    function goBack() { router.push('/device-management/device-list') }
    return { specificPart, goBack, ArrowLeft }
  },
}
</script>

<style scoped>
.device-management-settings { padding: 0; }
.page-head { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 20px; }
.ph-accent { width: 4px; height: 44px; border-radius: 2px; background: linear-gradient(180deg, var(--acc), var(--acc-2)); flex-shrink: 0; margin-top: 2px; }
.ph-title { margin: 0; font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--ink-0); line-height: 1.3; }
.ph-sub { margin: 4px 0 0 0; font-size: var(--font-size-sm); color: var(--ink-2); }
</style>
