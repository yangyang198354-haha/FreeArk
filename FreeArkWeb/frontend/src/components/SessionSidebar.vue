<!--
  @module MOD-FE-SIDEBAR
  @implements IFC-FE-SIDEBAR-001
  @depends MOD-FE-API (api.js)
  @author sub_agent_software_developer

  SessionSidebar — 左侧会话面板（v1.4）。
  v1.4 变更：会话列表项新增标题展示（session.title），降级显示"历史对话"。
  所有 HTTP 请求一律通过 api.js（REQ-NFUNC-002），禁止裸 axios。
-->
<template>
  <div class="session-sidebar">
    <div class="sidebar-header">
      <span class="sidebar-title">会话记录</span>
      <el-button type="primary" size="small" @click="handleNewSession" class="new-session-btn">
        新建会话
      </el-button>
    </div>

    <div class="session-list" v-loading="isLoading">
      <div v-if="!isLoading && sessions.length === 0" class="session-empty">
        暂无历史会话
      </div>

      <div
        v-for="session in sessions"
        :key="session.session_key_full"
        class="session-item"
        :class="{ 'session-item--active': session.session_key_full === currentSessionKey }"
        @click="handleSelectSession(session.session_key_full)"
      >
        <div class="session-info">
          <!-- IFC-FE-SIDEBAR-001: 标题展示，降级逻辑：title 为 null/空时显示"历史对话" -->
          <span class="session-title">
            {{ (session.title && session.title.trim().length > 0) ? session.title : '历史对话' }}
          </span>
          <span class="session-time">{{ formatTime(session.started_at) }}</span>
          <span class="session-count">{{ session.message_count }} 条消息</span>
        </div>
        <el-button
          class="delete-btn"
          size="small"
          type="danger"
          text
          @click.stop="handleDeleteSession(session.session_key_full)"
          title="删除会话"
        >
          <Trash2 :size="14" />
        </el-button>
      </div>
    </div>

    <el-dialog
      v-model="deleteDialogVisible"
      title="删除确认"
      width="300px"
      :close-on-click-modal="false"
    >
      <span>确定要删除这条会话记录吗？</span>
      <template #footer>
        <el-button @click="deleteDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmDelete" :loading="isDeleting">确定删除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Trash2 } from 'lucide-vue-next'
import api from '../utils/api.js'
import { chatSessionsCache, chatSessionsCacheTime } from '../router/index.js'
const CHAT_SESSIONS_CACHE_TTL_MS = 30000

export default {
  name: 'SessionSidebar',
  components: {
    Trash2,
  },
  props: {
    currentSessionKey: {
      type: String,
      default: null,
    },
  },
  emits: ['session-selected'],
  setup(props, { emit }) {
    const sessions = ref([])
    const isLoading = ref(false)
    const totalSessions = ref(0)
    const currentPage = ref(1)
    const sessionToDelete = ref(null)
    const deleteDialogVisible = ref(false)
    const isDeleting = ref(false)

    async function loadSessions(page, silent) {
      if (page === undefined) page = 1
      if (!silent) isLoading.value = true
      try {
        const data = await api.get('/api/memory/me/', { page: page, page_size: 20 })
        sessions.value = data.sessions || []
        totalSessions.value = data.total || 0
        currentPage.value = page
      } catch (err) {
        if (err && err.message !== 'SESSION_EXPIRED') {
          ElMessage.error('加载会话列表失败，请稍后重试')
        }
      } finally {
        isLoading.value = false
      }
    }

    function handleNewSession() {
      emit('session-selected', null)
    }

    function handleSelectSession(sessionKeyFull) {
      emit('session-selected', sessionKeyFull)
    }

    function handleDeleteSession(sessionKeyFull) {
      sessionToDelete.value = sessionKeyFull
      deleteDialogVisible.value = true
    }

    async function confirmDelete() {
      if (!sessionToDelete.value) return
      isDeleting.value = true
      const keyToDelete = sessionToDelete.value
      try {
        await api.delete(`/api/memory/session/${keyToDelete}/`)
        deleteDialogVisible.value = false
        sessionToDelete.value = null
        sessions.value = sessions.value.filter(s => s.session_key_full !== keyToDelete)
        totalSessions.value = Math.max(0, totalSessions.value - 1)
        if (keyToDelete === props.currentSessionKey) {
          emit('session-selected', null)
        }
      } catch (err) {
        if (err && err.message !== 'SESSION_EXPIRED') {
          ElMessage.error('删除会话失败，请稍后重试')
        }
      } finally {
        isDeleting.value = false
      }
    }

    function formatTime(isoStr) {
      if (!isoStr) return ''
      try {
        const d = new Date(isoStr)
        const month = String(d.getMonth() + 1).padStart(2, '0')
        const day = String(d.getDate()).padStart(2, '0')
        const hour = String(d.getHours()).padStart(2, '0')
        const min = String(d.getMinutes()).padStart(2, '0')
        return `${month}-${day} ${hour}:${min}`
      } catch (_) {
        return isoStr
      }
    }

    onMounted(() => {
      // 若路由预取缓存有效（30s 内），直接渲染，避免首屏等待
      const now = Date.now()
      if (chatSessionsCache && (now - chatSessionsCacheTime) < CHAT_SESSIONS_CACHE_TTL_MS) {
        sessions.value = chatSessionsCache.sessions || []
        totalSessions.value = chatSessionsCache.total || 0
        currentPage.value = 1
        // 后台静默刷新（确保数据最新）
        loadSessions(1, /* silent= */ true)
      } else {
        loadSessions(1)
      }
    })

    return {
      sessions,
      isLoading,
      totalSessions,
      currentPage,
      sessionToDelete,
      deleteDialogVisible,
      isDeleting,
      loadSessions,
      handleNewSession,
      handleSelectSession,
      handleDeleteSession,
      confirmDelete,
      formatTime,
    }
  },
}
</script>

<style scoped>
.session-sidebar {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-card, #1E293B);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-base, 6px);
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 12px 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.sidebar-title {
  font-size: var(--font-size-sm, 12px);
  font-weight: var(--font-weight-semibold, 600);
  color: var(--ink-2, #94A3B8);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.new-session-btn {
  font-size: var(--font-size-xs, 11px);
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px 0;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.1) transparent;
}

.session-list::-webkit-scrollbar {
  width: 4px;
}

.session-list::-webkit-scrollbar-track {
  background: transparent;
}

.session-list::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}

.session-empty {
  padding: 32px 14px;
  text-align: center;
  font-size: var(--font-size-sm, 12px);
  color: var(--ink-2, #64748B);
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px 8px 14px;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: background-color 0.15s, border-color 0.15s;
}

.session-item:hover {
  background-color: var(--color-bg-sidebar-hover, rgba(255, 255, 255, 0.06));
}

.session-item--active {
  background-color: var(--color-bg-sidebar-active, rgba(30, 74, 138, 0.35));
  border-left-color: var(--acc, #3B82F6);
}

.session-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.session-title {
  font-size: var(--font-size-sm, 12px);
  color: var(--color-text-primary, #E2E8F0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

.session-time {
  font-size: var(--font-size-xs, 11px);
  color: var(--ink-2, #64748B);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-count {
  font-size: var(--font-size-xs, 11px);
  color: var(--ink-2, #64748B);
}

.delete-btn {
  opacity: 0;
  transition: opacity 0.15s;
  flex-shrink: 0;
  color: var(--color-danger, #EF4444) !important;
}

.session-item:hover .delete-btn {
  opacity: 1;
}
</style>
