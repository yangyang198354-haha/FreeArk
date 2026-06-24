<!--
  @module MOD-PAGE-CHAT-INDEX
  @author sub_agent_software_developer
  @description Chat session list page (US-11, slice 1).
    Lists sessions from GET /api/memory/me/ with pagination.
    "New session" button → session page directly (backend LLM auto-routes the expert;
    expert选择对用户隐藏，与现有 Web ChatView 一致).
    Tapping existing session → session page with session_key param.
    Refreshes session list on every onShow.
-->
<template>
  <view class="chat-index-page">
    <!-- New session button：后端 LLM 自动路由，不向用户暴露专家选择 -->
    <view class="new-session-bar">
      <button class="btn-new-session" @tap="startNewSession">+ 新建会话</button>
    </view>

    <!-- Session list with pull-to-refresh and infinite scroll -->
    <scroll-view
      scroll-y
      class="session-list"
      @scrolltolower="loadMore"
      refresher-enabled
      :refresher-triggered="refreshing"
      @refresherrefresh="onRefresh"
    >
      <view v-if="sessions.length === 0 && !loading" class="empty-state">
        <text class="empty-text">暂无会话历史，点击「新建会话」开始</text>
      </view>

      <view
        v-for="session in sessions"
        :key="session.session_key || session.id"
        class="session-item"
        @tap="openSession(session)"
      >
        <view class="session-top">
          <text class="session-summary">
            {{ session.summary || (session.session_key ? session.session_key.slice(0, 8) : '新会话') }}
          </text>
          <text class="session-time">{{ formatTime(session.last_message_time || session.updated_at) }}</text>
        </view>
      </view>

      <view v-if="loading" class="loading-tip"><text>加载中…</text></view>
      <view v-if="noMore && sessions.length > 0" class="no-more-tip"><text>没有更多了</text></view>
    </scroll-view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { useAuthStore } from '@/store/auth'
import { useChatStore } from '@/store/chat'
import { api } from '@/utils/api'

const authStore = useAuthStore()
const chatStore = useChatStore()

// Auth guard
if (!authStore.isLoggedIn) {
  uni.reLaunch({ url: '/pages/login/index' })
}

const sessions = ref([])
const loading = ref(false)
const refreshing = ref(false)
const noMore = ref(false)
const page = ref(1)
const PAGE_SIZE = 20

async function loadSessions(reset = false) {
  if (loading.value) return
  if (reset) {
    page.value = 1
    noMore.value = false
  }
  loading.value = true
  try {
    const res = await api.getSessionList({ page: page.value, page_size: PAGE_SIZE })
    // Support both DRF paginated (results) and custom (data) response shapes
    const items = res?.results || res?.data || []
    if (reset) {
      sessions.value = items
    } else {
      sessions.value = [...sessions.value, ...items]
    }
    if (items.length < PAGE_SIZE) noMore.value = true
    page.value++
  } catch (err) {
    uni.showToast({ title: '加载会话列表失败', icon: 'none' })
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function loadMore() {
  if (!noMore.value) loadSessions()
}

async function onRefresh() {
  refreshing.value = true
  await loadSessions(true)
}

// Refresh list every time this tab/page becomes visible
onShow(() => {
  if (!authStore.isLoggedIn) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  loadSessions(true)
})

function openSession(session) {
  const key = session.session_key || session.key
  uni.navigateTo({
    url: `/subpackages/chat/pages/session?session_key=${key}`,
  })
}

function startNewSession() {
  // 新建会话直接进入聊天页；后端 LLM 自动路由专家，不传 expert_type
  chatStore.resetSession()
  uni.navigateTo({ url: '/subpackages/chat/pages/session' })
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
  return `${d.getMonth() + 1}/${d.getDate()}`
}
</script>

<style scoped>
.chat-index-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f5f5f5;
}
.new-session-bar {
  padding: 20rpx 24rpx;
  background: #fff;
  border-bottom: 1rpx solid #eee;
  flex-shrink: 0;
}
.btn-new-session {
  background: #1a73e8;
  color: #fff;
  font-size: 28rpx;
  border-radius: 48rpx;
  padding: 0 48rpx;
  height: 80rpx;
  line-height: 80rpx;
  border: none;
}
.session-list {
  flex: 1;
}
.session-item {
  background: #fff;
  margin: 12rpx 24rpx;
  border-radius: 12rpx;
  padding: 24rpx;
  box-shadow: 0 2rpx 6rpx rgba(0,0,0,0.06);
}
.session-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8rpx;
}
.session-summary {
  font-size: 28rpx;
  color: #333;
  flex: 1;
  margin-right: 16rpx;
}
.session-time {
  font-size: 22rpx;
  color: #999;
  flex-shrink: 0;
}
.empty-state {
  padding: 80rpx 48rpx;
  text-align: center;
}
.empty-text {
  color: #999;
  font-size: 28rpx;
}
.loading-tip,
.no-more-tip {
  text-align: center;
  padding: 24rpx;
  font-size: 24rpx;
  color: #999;
}
</style>
