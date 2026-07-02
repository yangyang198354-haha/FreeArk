<!--
  @module MOD-PAGE-BIND
  @description 专有部分绑定管理页（v1.8.0，REQ-BIND-001 ~ REQ-BIND-004）。
    - 顶部：扫码绑定（uni.scanCode 取 OwnerInfo.unique_id / screenMAC）或手动输入 MAC 绑定
    - 列表：当前已绑定的专有部分（api.getBindStatus），每项可自助解绑（api.unbindOwner）
    - 合并 bind + unbind + status 于单页，符合小程序 pages/<name>/index.vue 约定
    - 多对多：一个账号可绑定多个专有部分；重复绑定后端返回 409 提示
-->
<template>
  <view class="bind-page">
    <!-- 新增绑定 -->
    <view class="card">
      <text class="card-title">绑定专有部分</text>
      <text class="card-hint">扫描设备屏上的二维码，或手动输入 MAC 地址完成绑定</text>
      <button class="scan-btn" :disabled="binding" @tap="handleScan">扫码绑定</button>
      <view class="input-row">
        <input class="mac-input" type="text" v-model="macInput" placeholder="手动输入 MAC 地址" placeholder-class="ph" :disabled="binding" />
        <button class="bind-btn" :loading="binding" :disabled="binding || !macInput.trim()" @tap="bindByInput">绑定</button>
      </view>
    </view>

    <!-- 已绑定列表 -->
    <view class="card">
      <text class="card-title">我的专有部分</text>
      <view v-if="loading" class="empty"><text>加载中…</text></view>
      <view v-else-if="bindings.length === 0" class="empty"><text>暂无绑定，请先扫码或输入 MAC 绑定</text></view>
      <view v-else>
        <view class="bind-item" v-for="b in bindings" :key="b.specific_part">
          <view class="bi-info">
            <text class="bi-part">{{ b.specific_part }}</text>
            <text class="bi-loc">{{ b.location_name || '—' }}</text>
          </view>
          <button class="unbind-btn" size="mini" :disabled="binding" @tap="handleUnbind(b)">解绑</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { useOwnerStore } from '@/store/owner'
import { api } from '@/utils/api'

const authStore = useAuthStore()
const ownerStore = useOwnerStore()
const bindings = computed(() => ownerStore.bindings)
const loading = ref(false)
const binding = ref(false)
const macInput = ref('')

onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  loadStatus()
})

async function loadStatus(force = false) {
  loading.value = force || !ownerStore.bindingsLoaded
  try {
    await ownerStore.ensureBindings({ force, allowStale: !force })
  } catch (err) {
    uni.showToast({ title: '加载绑定状态失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function handleScan() {
  uni.scanCode({
    success: (res) => {
      const code = (res.result || '').trim()
      if (!code) {
        uni.showToast({ title: '未识别到有效内容', icon: 'none' })
        return
      }
      doBind(code)
    },
    fail: () => { /* 用户取消扫码，不提示 */ },
  })
}

function bindByInput() {
  const v = macInput.value.trim()
  if (!v) return
  doBind(v)
}

async function doBind(uniqueId) {
  binding.value = true
  try {
    const res = await api.bindOwner({ unique_id: uniqueId })
    uni.showToast({ title: `绑定成功：${res.specific_part}`, icon: 'none', duration: 2000 })
    macInput.value = ''
    ownerStore.markBindingChanged()
    await loadStatus(true)
  } catch (err) {
    const m = err.message || ''
    const msg =
      m.includes('HTTP 404') ? '未找到对应专有部分，请确认二维码/MAC' :
      m.includes('HTTP 409') ? '您已绑定该专有部分' :
      m.includes('HTTP 400') ? 'MAC 地址格式不正确' :
      '绑定失败，请稍后重试'
    uni.showToast({ title: msg, icon: 'none', duration: 2500 })
  } finally {
    binding.value = false
  }
}

function handleUnbind(b) {
  uni.showModal({
    title: '解绑确认',
    content: `确定解绑 ${b.specific_part} 吗？解绑后将无法查询该专有部分数据。`,
    success: async (r) => {
      if (!r.confirm) return
      binding.value = true
      try {
        await api.unbindOwner({ specific_part: b.specific_part })
        uni.showToast({ title: '已解绑', icon: 'none' })
        ownerStore.markBindingChanged()
        await loadStatus(true)
      } catch (err) {
        uni.showToast({ title: '解绑失败，请稍后重试', icon: 'none' })
      } finally {
        binding.value = false
      }
    },
  })
}
</script>

<style scoped>
.bind-page { min-height: 100vh; background: #f5f5f5; padding: 24rpx; }
.card { background: #fff; border-radius: 16rpx; padding: 32rpx; margin-bottom: 24rpx; }
.card-title { display: block; font-size: 32rpx; font-weight: bold; color: #333; margin-bottom: 8rpx; }
.card-hint { display: block; font-size: 24rpx; color: #999; margin-bottom: 24rpx; }
.scan-btn { background: #1a73e8; color: #fff; font-size: 30rpx; border-radius: 12rpx; height: 88rpx; line-height: 88rpx; border: none; margin-bottom: 20rpx; }
.input-row { display: flex; align-items: center; gap: 16rpx; }
.mac-input { flex: 1; height: 80rpx; border: 2rpx solid #e0e0e0; border-radius: 12rpx; padding: 0 24rpx; font-size: 28rpx; background: #fafafa; }
.ph { color: #bbb; }
.bind-btn { background: #1a73e8; color: #fff; font-size: 28rpx; border-radius: 12rpx; height: 80rpx; line-height: 80rpx; border: none; padding: 0 32rpx; }
.bind-btn[disabled] { opacity: 0.5; }
.empty { text-align: center; color: #999; font-size: 28rpx; padding: 40rpx 0; }
.bind-item { display: flex; align-items: center; justify-content: space-between; padding: 24rpx 0; border-bottom: 2rpx solid #f0f0f0; }
.bind-item:last-child { border-bottom: none; }
.bi-info { display: flex; flex-direction: column; }
.bi-part { font-size: 30rpx; font-weight: bold; color: #333; }
.bi-loc { font-size: 24rpx; color: #999; margin-top: 6rpx; }
.unbind-btn { background: #fff; color: #f44336; border: 2rpx solid #f44336; font-size: 26rpx; border-radius: 10rpx; line-height: 1.8; }
.unbind-btn[disabled] { opacity: 0.5; }
</style>
