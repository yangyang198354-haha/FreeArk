<!--
  @module MOD-COMPONENT-CHATBUBBLE
  @author sub_agent_software_developer
  @description Chat message bubble for AI and user messages.
    Supports two themes: 'light' (default, for subpackages/chat) and 'cyberpunk' (for pages/chat).

  MARKDOWN RENDERING:
  After stream_end, the assistant content is rendered as Markdown via miniMarkdown
  into the native <rich-text> component. rich-text whitelists tags (no scripts) so
  it is inherently XSS-safe. During streaming we keep raw <text> (incremental tokens
  are plain markdown source).

  THEME NOTES:
  <rich-text> does NOT propagate scoped/page CSS into its inner nodes in WeChat mini programs.
  For the cyberpunk theme, we inject inline styles via a wrapper <div> so inner elements
  (tables, code blocks, blockquotes, links) render with correct dark-theme colors.
  The light theme relies on browser-default rendering which works well on white backgrounds.
-->
<template>
  <view
    class="bubble-wrapper"
    :class="[
      role === 'user' ? 'bubble-wrapper--user' : 'bubble-wrapper--ai',
      theme === 'cyberpunk' ? 'bubble-wrapper--cyber' : ''
    ]"
  >
    <view
      class="bubble"
      :class="[
        role === 'user' ? 'bubble--user' : 'bubble--ai',
        theme === 'cyberpunk' ? 'bubble--cyber' : ''
      ]"
    >
      <!-- Reasoning area (shown during/after reasoning phase) -->
      <view v-if="reasoning" class="reasoning-box" :class="theme === 'cyberpunk' ? 'reasoning-box--cyber' : ''">
        <text class="reasoning-label" :class="theme === 'cyberpunk' ? 'reasoning-label--cyber' : ''">思考过程</text>
        <text class="reasoning-text" :class="theme === 'cyberpunk' ? 'reasoning-text--cyber' : ''">{{ reasoning }}</text>
      </view>

      <!-- Thinking placeholder: shown during streaming before any content arrives -->
      <text
        v-if="streaming && !content && !reasoning"
        class="thinking-text"
        :class="theme === 'cyberpunk' ? 'thinking-text--cyber' : ''"
      >
        {{ statusText || '正在思考…' }}
      </text>

      <!-- During streaming: plain text with cursor -->
      <text v-if="streaming && content" class="bubble-text">{{ content }}<text class="cursor">|</text></text>

      <!-- After stream_end: render Markdown via miniMarkdown → native rich-text -->
      <rich-text v-if="!streaming && content" class="bubble-rich" :class="theme === 'cyberpunk' ? 'bubble-rich--cyber' : ''" :nodes="renderedHtml" />

      <!-- Confirm card for Tier-2 write operations (confirm_required WS frame) -->
      <view v-if="confirmActions" class="confirm-card" :class="theme === 'cyberpunk' ? 'confirm-card--cyber' : ''">
        <text class="confirm-title" :class="theme === 'cyberpunk' ? 'confirm-title--cyber' : ''">待确认操作</text>
        <view v-for="(a, i) in confirmActions" :key="i" class="confirm-item">
          <text :class="theme === 'cyberpunk' ? 'confirm-item--cyber' : ''">{{ a.preview || JSON.stringify(a) }}</text>
        </view>
        <view class="confirm-buttons">
          <button class="btn-confirm" :class="theme === 'cyberpunk' ? 'btn-confirm--cyber' : ''" @tap="$emit('confirm', true)">确认</button>
          <button class="btn-cancel" :class="theme === 'cyberpunk' ? 'btn-cancel--cyber' : ''" @tap="$emit('confirm', false)">取消</button>
        </view>
      </view>

    </view>
  </view>
</template>

<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '@/utils/miniMarkdown'

const props = defineProps({
  role: { type: String, default: 'assistant' },
  content: { type: String, default: '' },
  streaming: { type: Boolean, default: false },
  reasoning: { type: String, default: '' },
  statusText: { type: String, default: '' },
  confirmActions: { type: Array, default: null },
  theme: { type: String, default: 'light' },  // 'light' | 'cyberpunk'
})
defineEmits(['confirm'])

// Markdown → HTML for rich-text. Falls back to raw text on any parse error.
// Cyberpunk theme: wrap output in a <div> with inline dark-theme styles since
// <rich-text> does NOT inherit page-level CSS for inner nodes in WeChat.
const renderedHtml = computed(() => {
  if (!props.content) return ''
  try {
    const mdHtml = renderMarkdown(props.content)
    if (props.theme === 'cyberpunk') {
      // Inline styles are the ONLY reliable way to style inner rich-text nodes
      // in WeChat mini programs (scoped CSS + global CSS both fail to penetrate).
      return `<div style="color:#dbeeff;font-size:14px;line-height:1.65">${mdHtml}</div>`
    }
    return mdHtml
  } catch {
    return props.content
  }
})
</script>

<style scoped>
/* ========== LIGHT THEME (default, session.vue) ========== */
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

/* ========== CYBERPUNK THEME (pages/chat/index.vue) ========== */
.bubble-wrapper--cyber {
  margin: 0;
}
.bubble-wrapper--ai.bubble-wrapper--cyber {
  justify-content: flex-start;
}
.bubble-wrapper--user.bubble-wrapper--cyber {
  justify-content: flex-end;
}

/* Cyberpunk bubble base: match index.vue .bubble styles */
.bubble--cyber {
  max-width: 78%;
  padding: 22rpx 26rpx;
  word-break: break-word;
}

/* AI bubble — cyberpunk (matches .bubble-ai in index.vue) */
.bubble--ai.bubble--cyber {
  background: rgba(14,22,42,0.85);
  border: 1px solid rgba(56,230,224,0.2);
  border-radius: 10rpx 28rpx 28rpx 28rpx;
  box-shadow: 0 0 12px rgba(47,244,224,0.15);
}

/* User bubble — cyberpunk (matches .bubble-user in index.vue) */
.bubble--user.bubble--cyber {
  background: linear-gradient(95deg, #22e6da, #3a8bff);
  border-radius: 28rpx 10rpx 28rpx 28rpx;
  box-shadow: 0 0 18px rgba(47,244,224,0.3);
}

/* Streaming text — cyberpunk */
.bubble--cyber .bubble-text {
  font-size: 27rpx;
  line-height: 1.65;
  word-break: break-all;
}
.bubble--ai.bubble--cyber .bubble-text {
  color: #dbeeff;
}
.bubble--user.bubble--cyber .bubble-text {
  color: #04121f;
  font-weight: 600;
  line-height: 1.55;
}

/* rich-text component — cyberpunk */
.bubble-rich--cyber {
  font-size: 27rpx;
  line-height: 1.65;
  word-break: break-word;
}

/* Cursor — cyberpunk */
.bubble--cyber .cursor {
  color: #2ff4e0;
}

/* Thinking — cyberpunk */
.thinking-text--cyber {
  color: #ffc83c;
  font-size: 24rpx;
}

/* Reasoning — cyberpunk */
.reasoning-box--cyber {
  background: rgba(47,244,224,0.06);
  border: 1px solid rgba(56,230,224,0.15);
  border-radius: 8rpx;
  padding: 12rpx;
  margin-bottom: 12rpx;
}
.reasoning-label--cyber {
  font-size: 22rpx;
  color: #7df9ff;
  display: block;
  margin-bottom: 6rpx;
}
.reasoning-text--cyber {
  font-size: 24rpx;
  color: rgba(143,217,255,0.7);
}

/* Confirm card — cyberpunk */
.confirm-card--cyber {
  background: rgba(255,212,0,0.08);
  border: 1px solid rgba(255,212,0,0.25);
  border-radius: 8rpx;
  padding: 16rpx;
  margin-top: 12rpx;
}
.confirm-title--cyber {
  font-weight: bold;
  font-size: 26rpx;
  color: #ffd400;
  display: block;
  margin-bottom: 8rpx;
}
.confirm-item--cyber {
  font-size: 24rpx;
  color: rgba(255,255,255,0.65);
  margin-bottom: 6rpx;
}
.btn-confirm--cyber {
  background: rgba(0,255,163,0.18);
  border: 1px solid rgba(0,255,163,0.6);
  color: #00ffa3;
  font-size: 24rpx;
  border-radius: 10rpx;
  padding: 14rpx 24rpx;
  line-height: 1.4;
}
.btn-cancel--cyber {
  background: rgba(255,46,99,0.15);
  border: 1px solid rgba(255,46,99,0.5);
  color: #ff5c85;
  font-size: 24rpx;
  border-radius: 10rpx;
  padding: 14rpx 24rpx;
  line-height: 1.4;
}
</style>
