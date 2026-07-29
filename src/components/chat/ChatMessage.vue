<template>
  <div class="chat-message" :class="[`role-${message.role}`, { streaming: message.isStreaming }]">
    <!-- 头像 -->
    <div class="msg-avatar">
      <template v-if="message.role === 'user'">
        <a-avatar :size="36" class="avatar-user">
          <template #icon><UserOutlined /></template>
        </a-avatar>
      </template>
      <template v-else>
        <a-avatar :size="36" class="avatar-ai">
          <template #icon><RobotOutlined /></template>
        </a-avatar>
      </template>
    </div>

    <!-- 消息内容 -->
    <div class="msg-body">
      <div class="msg-header">
        <span class="msg-role">{{ message.role === 'user' ? userName : '燕麦 · AI 助手' }}</span>
        <span class="msg-time">{{ formatTime(message.timestamp) }}</span>
      </div>

      <!-- 用户消息 -->
      <div v-if="message.role === 'user'" class="msg-content user-content">
        {{ message.content }}
      </div>

      <!-- AI 回答 -->
      <div v-else class="msg-content ai-content">
        <div class="markdown-body" v-html="renderedContent" ref="contentRef" />

        <span v-if="message.isStreaming" class="streaming-cursor">▌</span>

        <div v-if="message.confidence !== undefined && !message.isStreaming" class="msg-meta">
          <span class="confidence-badge" :class="confidenceClass">
            <CheckCircleOutlined v-if="message.confidence >= 0.7" />
            <ExclamationCircleOutlined v-else />
            置信度 {{ (message.confidence * 100).toFixed(0) }}%
          </span>
          <span v-if="message.tokenUsage" class="token-info">
            {{ message.tokenUsage.total_tokens }} tokens
          </span>
        </div>

        <!-- 引用来源 -->
        <div v-if="message.sources && message.sources.length > 0 && !message.isStreaming" class="msg-sources">
          <div class="sources-title">参考来源 ({{ message.sources.length }})</div>
          <SourceCard
            v-for="s in message.sources"
            :key="s.ref"
            :source="s"
          />
        </div>

        <!-- 复制按钮 -->
        <div v-if="message.content && !message.isStreaming" class="msg-actions">
          <a-button type="text" size="small" @click="copyContent">
            <template #icon><CopyOutlined /></template>
            {{ copied ? '已复制' : '复制' }}
          </a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { marked } from 'marked'
import {
  UserOutlined,
  RobotOutlined,
  CopyOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons-vue'
import { message as antMessage } from 'ant-design-vue'
import SourceCard from './SourceCard.vue'
import type { ChatMessage } from '@/types/rag'

const props = withDefaults(defineProps<{
  message: ChatMessage
  userName?: string
}>(), {
  userName: '我',
})

marked.setOptions({
  breaks: true,
  gfm: true,
})

const renderedContent = computed(() => {
  if (!props.message.content) return ''
  try {
    return marked.parse(props.message.content) as string
  } catch {
    return escapeHtml(props.message.content)
  }
})

function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  }
  return text.replace(/[&<>"']/g, (ch) => map[ch] || ch)
}

const copied = ref(false)

async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.message.content)
    copied.value = true
    antMessage.success('已复制到剪贴板')
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    antMessage.error('复制失败')
  }
}

const confidenceClass = computed(() => {
  if (!props.message.confidence) return ''
  if (props.message.confidence >= 0.8) return 'confidence-high'
  if (props.message.confidence >= 0.6) return 'confidence-medium'
  return 'confidence-low'
})

function formatTime(ts: number): string {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}
</script>

<style scoped lang="less">
.chat-message {
  display: flex;
  gap: 12px;
  padding: 18px 20px;
  animation: msgIn 0.35s ease;

  &.role-user {
    flex-direction: row-reverse;

    .msg-body {
      align-items: flex-end;
    }

    .msg-header {
      justify-content: flex-end;
    }
  }

  &:hover .msg-actions {
    opacity: 1;
  }
}

@keyframes msgIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.msg-avatar {
  flex-shrink: 0;
  padding-top: 2px;
}

.avatar-user {
  background: linear-gradient(135deg, #D4A373, #B8860B);
}

.avatar-ai {
  background: linear-gradient(135deg, rgba(74, 108, 247, 0.6), rgba(0, 212, 255, 0.4));
  border: 1px solid rgba(74, 108, 247, 0.3);
}

.msg-body {
  display: flex;
  flex-direction: column;
  max-width: 72%;
  min-width: 100px;
}

.msg-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.msg-role {
  font-size: 12px;
  font-weight: 600;
  color: #94A3B8;
}

.msg-time {
  font-size: 11px;
  color: #475569;
}

.msg-content {
  border-radius: 14px;
  line-height: 1.7;

  &.user-content {
    padding: 10px 18px;
    background: linear-gradient(135deg, rgba(212, 163, 115, 0.30), rgba(184, 134, 11, 0.15));
    color: #F8FAFC;
    font-size: 14px;
    border-bottom-right-radius: 4px;
    word-break: break-word;
    white-space: pre-wrap;
    border: 1px solid rgba(212, 163, 115, 0.15);
  }

  &.ai-content {
    padding: 6px 0;
    font-size: 14px;
    color: #E2E8F0;
    word-break: break-word;
  }
}

/* ── Markdown 内容样式 (深色主题) ── */
.markdown-body {
  :deep(p) {
    margin: 0.4em 0;
  }

  :deep(h1), :deep(h2), :deep(h3), :deep(h4) {
    margin: 1em 0 0.4em;
    font-weight: 600;
    color: #F8FAFC;
  }

  :deep(h1) { font-size: 1.4em; }
  :deep(h2) { font-size: 1.2em; }
  :deep(h3) { font-size: 1.05em; }

  :deep(code) {
    padding: 2px 6px;
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.08);
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.88em;
    color: #FBBF24;
  }

  :deep(pre) {
    margin: 12px 0;
    padding: 16px 18px;
    border-radius: 10px;
    background: rgba(0, 0, 0, 0.40);
    border: 1px solid rgba(255, 255, 255, 0.06);
    overflow-x: auto;

    code {
      padding: 0;
      background: none;
      color: #E2E8F0;
      font-size: 13px;
      line-height: 1.65;
    }
  }

  :deep(blockquote) {
    margin: 8px 0;
    padding: 10px 16px;
    border-left: 3px solid #D4A373;
    background: rgba(212, 163, 115, 0.06);
    border-radius: 0 8px 8px 0;
    color: #94A3B8;
    font-style: italic;
  }

  :deep(ul), :deep(ol) {
    padding-left: 1.4em;
    margin: 0.4em 0;
  }

  :deep(li) {
    margin: 2px 0;
  }

  :deep(a) {
    color: #4A6CF7;
    text-decoration: none;
    &:hover { text-decoration: underline; color: #00D4FF; }
  }

  :deep(table) {
    margin: 12px 0;
    border-collapse: collapse;
    width: 100%;
    font-size: 13px;

    th, td {
      padding: 8px 12px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      text-align: left;
    }

    th {
      background: rgba(255, 255, 255, 0.05);
      color: #F8FAFC;
      font-weight: 600;
    }

    td {
      color: #CBD5E1;
    }
  }

  :deep(hr) {
    margin: 16px 0;
    border: none;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }

  :deep(img) {
    max-width: 100%;
    border-radius: 8px;
  }
}

/* ── 流式光标 ── */
.streaming-cursor {
  display: inline;
  animation: blink 0.8s infinite;
  color: #D4A373;
  font-weight: 400;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* ── 置信度 ── */
.msg-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  font-size: 12px;
}

.confidence-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 12px;
  font-weight: 500;

  &.confidence-high {
    background: rgba(52, 211, 153, 0.12);
    color: #34D399;
    border: 1px solid rgba(52, 211, 153, 0.2);
  }

  &.confidence-medium {
    background: rgba(251, 191, 36, 0.12);
    color: #FBBF24;
    border: 1px solid rgba(251, 191, 36, 0.2);
  }

  &.confidence-low {
    background: rgba(248, 113, 113, 0.12);
    color: #F87171;
    border: 1px solid rgba(248, 113, 113, 0.2);
  }
}

.token-info {
  color: #475569;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
}

/* ── 引用来源 ── */
.msg-sources {
  margin-top: 12px;
}

.sources-title {
  font-size: 12px;
  font-weight: 600;
  color: #64748B;
  margin-bottom: 8px;
}

/* ── 操作按钮 ── */
.msg-actions {
  margin-top: 8px;
  opacity: 0;
  transition: opacity 0.2s;

  :deep(.ant-btn-text) {
    color: #64748B;
    &:hover { color: #D4A373; }
  }
}
</style>
