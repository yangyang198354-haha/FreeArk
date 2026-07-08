<!--
  @module MOD-BD-010
  @implements IFC-BD-010-01, IFC-BD-010-02, IFC-BD-010-03, IFC-BD-010-04, IFC-BD-010-05, IFC-BD-010-06
  @depends none
  @description Multi-cockpit switcher for owners with multiple bound specific_parts.
    Uses uni-app <picker> component. Hidden when bindings.length <= 1.
-->
<template>
  <view v-if="visible" class="cabin-switcher">
    <picker
      mode="selector"
      :range="labels"
      :value="selectedIndex"
      @change="onChange"
    >
      <view class="switcher-picker">
        <text class="switcher-label">当前座舱</text>
        <text class="switcher-value">{{ currentLabel }} ›</text>
      </view>
    </picker>
  </view>
</template>

<script setup>
import { computed } from 'vue'

/**
 * IFC-BD-010-01: Binding list [{specific_part, location_name}].
 * IFC-BD-010-02: Currently selected index.
 * IFC-BD-010-03: Whether to show the switcher (bindings.length > 1).
 */
const props = defineProps({
  bindings: { type: Array, default: () => [] },
  selectedIndex: { type: Number, default: 0 },
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['change'])

/** IFC-BD-010-05: Labels for picker range. */
const labels = computed(() =>
  props.bindings.map((b) => b.location_name || b.specific_part || '未命名')
)

/** IFC-BD-010-06: Current cockpit display name. */
const currentLabel = computed(() => {
  const b = props.bindings[props.selectedIndex]
  if (!b) return '未选择'
  return b.location_name || b.specific_part || '未命名'
})

/** IFC-BD-010-04: Emit @change with selected index. */
function onChange(e) {
  const idx = Number(e.detail.value)
  emit('change', idx)
}
</script>

<style scoped>
.cabin-switcher {
  padding: 10rpx 28rpx 0;
}

.switcher-picker {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18rpx 22rpx;
  border: 1rpx solid rgba(47, 244, 224, 0.22);
  background: rgba(7, 15, 32, 0.68);
}

.switcher-label {
  font-size: 22rpx;
  color: #6f8cad;
}

.switcher-value {
  max-width: 470rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 26rpx;
  color: #eaf6ff;
}
</style>
