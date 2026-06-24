<!--
  @module MOD-COMPONENT-CHATBUBBLE
  @author sub_agent_software_developer
  @description Chat message bubble for AI and user messages.

  MARKDOWN RENDERING:
  After stream_end, the assistant content is rendered as Markdown via `marked`
  (pure-JS MD→HTML) into the native <rich-text> component. rich-text whitelists
  tags (no scripts) so it is inherently XSS-safe; no DOM-based sanitizer needed.
  During streaming we keep raw <text> (incremental tokens are plain markdown source).
  Note: <rich-text> does not propagate scoped CSS into its inner nodes, so inner
  styling uses tag defaults — acceptable for the walking skeleton. If richer
  rendering is later required (clickable links / code highlighting), swap to
  towxml or mp-html per tech_stack.md OQ-07.
-->
<template>
  <view class="bubble-wrapper" :class="role === 'user' ? 'bubble-wrapper--user' : 'bubble-wrapper--ai'">
    <view class="bubble" :class="role === 'user' ? 'bubble--user' : 'bubble--ai'">

      <!-- Reasoning area (shown during/after reasoning phase) -->
      <view v-if="reasoning" class="reasoning-box">
        <text class="reasoning-label">思考过程</text>
        <text class="reasoning-text">{{ reasoning }}</text>
      </view>

      <!-- Thinking placeholder: shown during streaming before any content arrives -->
      <text v-if="streaming && !content && !reasoning" class="thinking-text">
        {{ statusText || '正在思考…' }}
      </text>

      <!-- During streaming: plain text with cursor -->
      <text v-if="streaming && content" class="bubble-text">{{ content }}<text class="cursor">|</text></text>

      <!-- After stream_end: render Markdown via marked → native rich-text -->
      <rich-text v-if="!streaming && content" class="bubble-rich" :nodes="renderedHtml" />

      <!-- Confirm card for Tier-2 write operations (confirm_required WS frame) -->
      <view v-if="confirmActions" class="confirm-card">
        <text class="confirm-title">待确认操作</text>
        <view v-for="(a, i) in confirmActions" :key="i" class="confirm-item">
          <text>{{ a.preview || JSON.stringify(a) }}</text>
        </view>
        <view class="confirm-buttons">
          <button class="btn-confirm" @tap="$emit('confirm', true)">确认</button>
          <button class="btn-cancel" @tap="$emit('confirm', false)">取消</button>
        </view>
      </view>

    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  role: { type: String, default: 'assistant' },
  content: { type: String, default: '' },
  streaming: { type: Boolean, default: false },
  reasoning: { type: String, default: '' },
  statusText: { type: String, default: '' },
  confirmActions: { type: Array, default: null },
})
defineEmits(['confirm'])

// Markdown → HTML for rich-text. Falls back to raw text on any parse error.
const renderedHtml = computed(() => {
  if (!props.content) return ''
  try {
    return marked.parse(props.content, { breaks: true, gfm: true })
  } catch {
    return props.content
  }
})
</script>

<style scoped>
.bubble-wrapper {
  display: flex;
  margin: 12rpx 24rpx;
}
.bubble-wrapper--user {
  justify-content: flex-end;
}
.bubble-wrapper--ai {
  justify-content: flex-start;
}
.bubble {
  max-width: 75%;
  border-radius: 16rpx;
  padding: 20rpx 24rpx;
  word-break: break-all;
}
.bubble--user {
  background: #1a73e8;
}
.bubble--user .bubble-text {
  color: #fff;
  font-size: 28rpx;
  line-height: 1.6;
}
.bubble--ai {
  background: #fff;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.08);
}
.bubble--ai .bubble-text {
  color: #333;
  font-size: 28rpx;
  line-height: 1.6;
}
.bubble-rich {
  color: #333;
  font-size: 28rpx;
  line-height: 1.6;
  word-break: break-word;
}
.cursor {
  color: #1a73e8;
  animation: blink 1s infinite;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
.reasoning-box {
  background: #f5f5f5;
  border-radius: 8rpx;
  padding: 12rpx;
  margin-bottom: 12rpx;
}
.reasoning-label {
  font-size: 22rpx;
  color: #999;
  display: block;
  margin-bottom: 6rpx;
}
.reasoning-text {
  font-size: 24rpx;
  color: #666;
}
.thinking-text {
  color: #999;
  font-size: 26rpx;
  font-style: italic;
}
.confirm-card {
  background: #fff3cd;
  border-radius: 8rpx;
  padding: 16rpx;
  margin-top: 12rpx;
}
.confirm-title {
  font-weight: bold;
  font-size: 26rpx;
  color: #856404;
  display: block;
  margin-bottom: 8rpx;
}
.confirm-item {
  font-size: 24rpx;
  color: #666;
  margin-bottom: 6rpx;
}
.confirm-buttons {
  display: flex;
  gap: 16rpx;
  margin-top: 12rpx;
}
.btn-confirm {
  background: #1a73e8;
  color: #fff;
  font-size: 24rpx;
  border-radius: 8rpx;
  padding: 8rpx 24rpx;
  line-height: 1.4;
}
.btn-cancel {
  background: #f5f5f5;
  color: #666;
  font-size: 24rpx;
  border-radius: 8rpx;
  padding: 8rpx 24rpx;
  line-height: 1.4;
}
</style>
