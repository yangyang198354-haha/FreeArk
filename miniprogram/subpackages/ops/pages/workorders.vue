<!--
  @module MOD-PAGE-WORKORDERS
  @description 巡检工单（US-12 查看 + US-13 管理员审批）。对齐 Web WorkOrderListView：
    列表 GET /api/workorders/ {page,page_size} → {success,data,total}
    详情 GET /api/workorders/{id}/ → {success,data}
    管理员：POST /api/workorders/{id}/approve-write/（write_status==='PENDING' 时）、
           POST /api/workorders/{id}/resolve/（status 非 RESOLVED/CANCELLED 时）。
    字段：ticket_id,status,status_display,write_status,source_event_type,source_event_id,
         source_active,created_at,recommended_action(markdown)。
    管理员判断用 store.isAdmin(role==='admin')。顶部"工作日志"入口 → inspection-logs。
-->
<template>
  <view class="wo-page">
    <view class="wo-top">
      <text class="wo-title">巡检工单</text>
      <view class="wo-loglink" @tap="goLogs"><text>工作日志 ›</text></view>
    </view>

    <scroll-view scroll-y class="wo-list" @scrolltolower="loadMore" refresher-enabled :refresher-triggered="refreshing" @refresherrefresh="onRefresh">
      <view v-if="rows.length === 0 && !loading" class="empty"><text>暂无工单</text></view>

      <view v-for="row in rows" :key="row.id" class="card" @tap="openDetail(row)">
        <view class="card-top">
          <text class="ticket">{{ row.ticket_id }}</text>
          <text class="st" :class="stClass(row.status)">{{ row.status_display || row.status }}</text>
        </view>
        <view class="meta">
          <text class="meta-item">{{ sourceLabel(row.source_event_type) }} #{{ row.source_event_id }}</text>
          <text class="meta-item write" :class="writeClass(row.write_status)">{{ writeLabel(row.write_status) }}</text>
        </view>
        <text class="time">{{ fmt(row.created_at) }}</text>
      </view>

      <view v-if="loading" class="list-tip"><text>加载中…</text></view>
      <view v-if="noMore && rows.length > 0" class="list-tip"><text>没有更多了</text></view>
    </scroll-view>

    <!-- 详情浮层 -->
    <view v-if="detailVisible" class="overlay" @tap.self="detailVisible = false">
      <view class="sheet">
        <view class="sheet-head">
          <text class="sheet-title">{{ detail ? ('工单 ' + detail.ticket_id) : '工单详情' }}</text>
          <text class="sheet-close" @tap="detailVisible = false">✕</text>
        </view>
        <scroll-view scroll-y class="sheet-body">
          <view v-if="detailLoading" class="tip"><text>加载中…</text></view>
          <template v-else-if="detail">
            <view class="d-row"><text class="d-k">状态</text><text class="d-v">{{ detail.status_display || detail.status }}</text></view>
            <view class="d-row"><text class="d-k">来源</text><text class="d-v">{{ sourceLabel(detail.source_event_type) }} #{{ detail.source_event_id }}</text></view>
            <view class="d-row"><text class="d-k">写提案</text><text class="d-v">{{ writeLabel(detail.write_status) }}</text></view>
            <view class="d-block">
              <text class="d-k">建议处理</text>
              <rich-text class="d-rich" :nodes="recommendedHtml" />
            </view>
          </template>
        </scroll-view>

        <!-- 管理员操作 -->
        <view v-if="detail && isAdmin" class="sheet-actions">
          <button
            v-if="detail.write_status === 'PENDING'"
            class="btn btn-approve"
            :disabled="approving"
            @tap="approve"
          >{{ approving ? '执行中…' : '批准并下发写操作' }}</button>
          <button
            v-if="detail.status !== 'RESOLVED' && detail.status !== 'CANCELLED'"
            class="btn btn-resolve"
            :disabled="resolving"
            @tap="resolve"
          >{{ resolving ? '处理中…' : '标记已解决' }}</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { marked } from 'marked'
import { useAuthStore } from '@/store/auth'
import { api } from '@/utils/api'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin)

const WRITE_LABELS = { PENDING: '待审批', APPROVED: '已批准', EXECUTED: '已执行', REJECTED: '已拒绝', FAILED: '执行失败', NONE: '无写操作', NA: '—' }
const SOURCE_LABELS = { fault_event: '故障事件', condensation_warning_event: '结露预警' }

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const refreshing = ref(false)
const noMore = ref(false)
const page = ref(1)
const PAGE_SIZE = 20

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref(null)
const approving = ref(false)
const resolving = ref(false)

const recommendedHtml = computed(() => {
  const md = detail.value && detail.value.recommended_action
  if (!md) return '<p style="color:#999">—</p>'
  try { return marked.parse(md, { breaks: true, gfm: true }) } catch { return md }
})

function fmt(s) { return s ? String(s).replace('T', ' ').slice(0, 16) : '—' }
function writeLabel(w) { return WRITE_LABELS[w] || w || '—' }
function sourceLabel(s) { return SOURCE_LABELS[s] || s || '—' }
function stClass(s) {
  if (s === 'RESOLVED') return 'st-done'
  if (s === 'CANCELLED') return 'st-cancel'
  return 'st-open'
}
function writeClass(w) { return w === 'PENDING' ? 'write-pending' : '' }

async function load(reset = false) {
  if (loading.value) return
  if (reset) { page.value = 1; noMore.value = false }
  loading.value = true
  try {
    const res = await api.getWorkOrders({ page: page.value, page_size: PAGE_SIZE })
    if (res && res.success && Array.isArray(res.data)) {
      rows.value = reset ? res.data : [...rows.value, ...res.data]
      total.value = res.total || rows.value.length
      if (res.data.length < PAGE_SIZE) noMore.value = true
      page.value++
    } else {
      if (reset) rows.value = []
      noMore.value = true
    }
  } catch (e) {
    uni.showToast({ title: '获取工单失败', icon: 'none' })
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function loadMore() { if (!noMore.value) load(false) }
async function onRefresh() { refreshing.value = true; await load(true) }

async function openDetail(row) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    const res = await api.getWorkOrderDetail(row.id)
    if (res && res.success) detail.value = res.data
    else uni.showToast({ title: '获取详情失败', icon: 'none' })
  } catch (e) {
    uni.showToast({ title: '获取详情失败', icon: 'none' })
  } finally {
    detailLoading.value = false
  }
}

async function approve() {
  if (!detail.value || approving.value) return
  approving.value = true
  try {
    const res = await api.approveWorkOrderWrite(detail.value.id)
    uni.showToast({ title: (res && res.message) || (res && res.success ? '已下发执行' : '执行失败'), icon: 'none' })
    if (res && res.success) { await openDetail(detail.value); load(true) }
  } catch (e) {
    uni.showToast({ title: '执行失败', icon: 'none' })
  } finally {
    approving.value = false
  }
}

async function resolve() {
  if (!detail.value || resolving.value) return
  resolving.value = true
  try {
    const res = await api.resolveWorkOrder(detail.value.id)
    uni.showToast({ title: (res && res.message) || (res && res.success ? '已标记解决' : '操作失败'), icon: 'none' })
    if (res && res.success) { await openDetail(detail.value); load(true) }
  } catch (e) {
    uni.showToast({ title: '操作失败', icon: 'none' })
  } finally {
    resolving.value = false
  }
}

function goLogs() { uni.navigateTo({ url: '/subpackages/ops/pages/inspection-logs' }) }

onShow(() => {
  if (!authStore.isLoggedIn) { uni.reLaunch({ url: '/pages/login/index' }); return }
  load(true)
})
</script>

<style scoped>
.wo-page { display: flex; flex-direction: column; height: 100vh; background: #f5f5f5; }
.wo-top { display: flex; align-items: center; justify-content: space-between; background: #fff; padding: 20rpx 24rpx; border-bottom: 1rpx solid #f0f0f0; flex-shrink: 0; }
.wo-title { font-size: 30rpx; font-weight: bold; color: #333; }
.wo-loglink text { font-size: 24rpx; color: #1a73e8; }
.wo-list { flex: 1; }
.empty { text-align: center; padding: 80rpx 24rpx; color: #999; font-size: 28rpx; }
.card { background: #fff; margin: 12rpx 24rpx; border-radius: 12rpx; padding: 20rpx 24rpx; box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8rpx; }
.ticket { font-size: 26rpx; font-weight: bold; color: #333; }
.st { font-size: 22rpx; padding: 2rpx 16rpx; border-radius: 20rpx; }
.st-open { background: #e8f0fe; color: #1a73e8; }
.st-done { background: #e6f4ea; color: #34a853; }
.st-cancel { background: #f0f0f0; color: #999; }
.meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6rpx; }
.meta-item { font-size: 22rpx; color: #888; }
.meta-item.write { padding: 2rpx 14rpx; border-radius: 16rpx; }
.write-pending { background: #fff4e5; color: #f59e0b; }
.time { font-size: 22rpx; color: #aaa; }
.list-tip { text-align: center; padding: 24rpx; font-size: 24rpx; color: #999; }
.overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: flex-end; z-index: 999; }
.sheet { width: 100%; max-height: 80vh; background: #fff; border-radius: 24rpx 24rpx 0 0; display: flex; flex-direction: column; }
.sheet-head { display: flex; justify-content: space-between; align-items: center; padding: 24rpx; border-bottom: 1rpx solid #f0f0f0; }
.sheet-title { font-size: 30rpx; font-weight: bold; color: #333; }
.sheet-close { font-size: 32rpx; color: #999; }
.sheet-body { padding: 16rpx 24rpx; max-height: 50vh; }
.tip { text-align: center; padding: 48rpx; color: #999; font-size: 28rpx; }
.d-row { display: flex; padding: 12rpx 0; border-bottom: 1rpx solid #f5f5f5; }
.d-k { font-size: 26rpx; color: #999; width: 140rpx; }
.d-v { font-size: 26rpx; color: #333; flex: 1; }
.d-block { padding: 16rpx 0; }
.d-rich { display: block; margin-top: 12rpx; font-size: 26rpx; color: #333; line-height: 1.6; }
.sheet-actions { padding: 16rpx 24rpx 32rpx; border-top: 1rpx solid #f0f0f0; }
.btn { width: 100%; height: 84rpx; line-height: 84rpx; border-radius: 12rpx; font-size: 28rpx; border: none; margin-top: 12rpx; }
.btn-approve { background: #1a73e8; color: #fff; }
.btn-resolve { background: #fff; color: #1a73e8; border: 2rpx solid #1a73e8; }
.btn[disabled] { opacity: 0.6; }
</style>
