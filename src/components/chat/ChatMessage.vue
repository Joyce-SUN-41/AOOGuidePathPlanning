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
        <span class="msg-role">{{ message.role === 'user' ? userName : '动麦 · AI 助手' }}</span>
        <span class="msg-time">{{ formatTime(message.timestamp) }}</span>
      </div>

      <!-- 用户消息 -->
      <div v-if="message.role === 'user'" class="msg-content user-content">
        {{ message.content }}
      </div>

      <!-- AI 回答 -->
      <div v-else class="msg-content ai-content">
        <div
          ref="contentRef"
          class="markdown-body"
          v-html="renderedContent"
          @mouseover="onContentHover"
          @mouseout="onContentLeave"
          @click="onContentClick"
        />

        <!-- 引用角标 Popover（事件委托驱动，跟随角标定位） -->
        <a-popover
          v-model:open="citePopoverOpen"
          :get-popup-container="getCitePopupContainer"
          placement="top"
          trigger="click"
          overlay-class-name="cite-popover"
          destroy-tooltip-on-hide
        >
          <template #content>
            <div v-if="activeCiteSource" class="cite-pop">
              <div class="cite-pop-head">
                <span class="cite-pop-ref">[{{ activeCiteSource.ref }}]</span>
                <span class="cite-pop-doc">{{ activeCiteSource.document }}</span>
              </div>
              <div class="cite-pop-sub">
                <span v-if="activeCiteSource.page">第 {{ activeCiteSource.page }} 页</span>
                <span v-if="activeCiteSource.section">{{ activeCiteSource.section }}</span>
                <span class="cite-pop-score">
                  相关度 {{ (activeCiteSource.score * 100).toFixed(0) }}%
                </span>
              </div>
              <p class="cite-pop-text">{{ citeExcerpt }}</p>
            </div>
          </template>
          <span
            class="cite-anchor"
            :style="{ left: citeAnchor.x + 'px', top: citeAnchor.y + 'px' }"
          />
        </a-popover>

        <span v-if="message.isStreaming" class="streaming-cursor">▌</span>

        <div v-if="message.confidence !== undefined && !message.isStreaming" class="msg-meta">
          <span class="confidence-ring" :class="confidenceClass">
            <a-progress
              type="circle"
              :percent="Math.round(message.confidence * 100)"
              :width="34"
              :stroke-width="10"
              :stroke-color="confidenceColor"
              trail-color="rgba(255,255,255,0.12)"
            >
              <template #format="{ percent }">
                <span class="ring-num">{{ percent }}</span>
              </template>
            </a-progress>
            <span class="ring-label">
              <CheckCircleOutlined v-if="message.confidence >= 0.7" />
              <ExclamationCircleOutlined v-else />
              置信度
            </span>
          </span>
          <span v-if="message.tokenUsage" class="token-info">
            {{ message.tokenUsage.total_tokens }} tokens
          </span>
        </div>

        <!-- 引用来源 -->
        <div
          v-if="message.sources && message.sources.length > 0 && !message.isStreaming"
          class="msg-sources"
        >
          <div class="sources-title">参考来源 ({{ message.sources.length }})</div>
          <SourceCard v-for="s in message.sources" :key="s.ref" :source="s" />
        </div>

        <!-- 复制按钮（建议 9：可复制素材未通过反思则锁定） -->
        <div v-if="message.content && !message.isStreaming" class="msg-actions">
          <a-tooltip
            v-if="copyLocked"
            title="完成反思（读懂并提问通过）后即可复制"
          >
            <a-button type="text" size="small" disabled>
              <template #icon><CopyOutlined /></template>
              复制
            </a-button>
          </a-tooltip>
          <a-button v-else type="text" size="small" @click="copyContent">
            <template #icon><CopyOutlined /></template>
            {{ copied ? '已复制' : '复制' }}
          </a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import {
  UserOutlined,
  RobotOutlined,
  CopyOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons-vue'
import { message as antMessage } from 'ant-design-vue'
import SourceCard from './SourceCard.vue'
import type { ChatMessage, RAGSource } from '@/types/rag'

const props = withDefaults(
  defineProps<{
    message: ChatMessage
    userName?: string
  }>(),
  {
    userName: '我'
  }
)

marked.setOptions({
  breaks: true,
  gfm: true
})

const renderedContent = computed(() => {
  if (!props.message.content) return ''
  try {
    const raw = marked.parse(props.message.content) as string
    const clean = DOMPurify.sanitize(raw, {
      ALLOWED_TAGS: [
        'h1',
        'h2',
        'h3',
        'h4',
        'h5',
        'h6',
        'p',
        'br',
        'strong',
        'em',
        'b',
        'i',
        'u',
        'a',
        'ul',
        'ol',
        'li',
        'code',
        'pre',
        'blockquote',
        'table',
        'thead',
        'tbody',
        'tr',
        'th',
        'td',
        'hr',
        'img',
        'span',
        'div',
        'del',
        'sup',
        'sub'
      ],
      ALLOWED_ATTR: [
        'href',
        'target',
        'rel',
        'src',
        'alt',
        'class',
        'id',
        'style',
        'colspan',
        'rowspan',
        'data-cite-ref'
      ],
      ALLOW_DATA_ATTR: false
    })
    return decorateCitations(clean)
  } catch {
    return escapeHtml(props.message.content)
  }
})

// ============ 引用角标处理 ============

/** ref -> source 映射 */
const sourceMap = computed(() => {
  const map = new Map<number, RAGSource>()
  for (const s of props.message.sources || []) map.set(s.ref, s)
  return map
})

/**
 * 把答案正文中的 [1] [2] 等引用标记替换为可交互的角标 <sup>。
 * 仅替换 sources 中真实存在的编号，避免误伤 markdown 链接与普通方括号内容。
 * 使用占位符规避 <a>/<code>/<pre> 内部的文本。
 */
function decorateCitations(html: string): string {
  if (sourceMap.value.size === 0) return html

  // 保护代码块与链接文本，防止其中的 [n] 被替换
  const guards: string[] = []
  const guarded = html.replace(/<(pre|code|a)\b[\s\S]*?<\/\1>/gi, (m) => {
    guards.push(m)
    return `\u0000GUARD${guards.length - 1}\u0000`
  })

  const replaced = guarded.replace(/\[(\d{1,2})\]/g, (whole, num: string) => {
    const ref = Number(num)
    if (!sourceMap.value.has(ref)) return whole
    return `<sup class="cite-mark" data-cite-ref="${ref}">${ref}</sup>`
  })

  return replaced.replace(/\u0000GUARD(\d+)\u0000/g, (_m, i: string) => guards[Number(i)] ?? '')
}

const contentRef = ref<HTMLElement | null>(null)
const citePopoverOpen = ref(false)
const activeCiteRef = ref<number | null>(null)
const citeAnchor = ref({ x: 0, y: 0 })
let hoverTimer: ReturnType<typeof setTimeout> | null = null

const activeCiteSource = computed(() =>
  activeCiteRef.value === null ? null : sourceMap.value.get(activeCiteRef.value) || null
)

/** 内容摘要，最多 160 字 */
const citeExcerpt = computed(() => {
  const text = activeCiteSource.value?.content?.trim() || ''
  return text.length > 160 ? text.slice(0, 160) + '…' : text
})

/** 气泡挂载到 markdown 容器内，保证 absolute 锚点定位生效 */
function getCitePopupContainer(): HTMLElement {
  return contentRef.value || document.body
}

function resolveCiteTarget(e: Event): HTMLElement | null {
  const el = e.target as HTMLElement | null
  if (!el || !el.dataset) return null
  return el.dataset['citeRef'] ? el : null
}

/** 定位角标锚点（相对 markdown 容器） */
function openCitePopover(el: HTMLElement) {
  const ref = Number(el.dataset['citeRef'])
  if (!sourceMap.value.has(ref)) return
  const host = contentRef.value
  if (!host) return
  const hostRect = host.getBoundingClientRect()
  const rect = el.getBoundingClientRect()
  citeAnchor.value = {
    x: rect.left - hostRect.left + rect.width / 2 + host.scrollLeft,
    y: rect.top - hostRect.top + host.scrollTop
  }
  activeCiteRef.value = ref
  citePopoverOpen.value = true
}

function onContentHover(e: MouseEvent) {
  const el = resolveCiteTarget(e)
  if (!el) return
  if (hoverTimer) clearTimeout(hoverTimer)
  hoverTimer = setTimeout(() => openCitePopover(el), 120)
}

function onContentLeave(e: MouseEvent) {
  if (!resolveCiteTarget(e)) return
  if (hoverTimer) {
    clearTimeout(hoverTimer)
    hoverTimer = null
  }
}

/** 点击角标（移动端无 hover）同样打开 */
function onContentClick(e: MouseEvent) {
  const el = resolveCiteTarget(e)
  if (!el) return
  e.preventDefault()
  openCitePopover(el)
}

onBeforeUnmount(() => {
  if (hoverTimer) clearTimeout(hoverTimer)
})

function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  }
  return text.replace(/[&<>"']/g, (ch) => map[ch] || ch)
}

const copied = ref(false)

// 建议 9：含可复制素材且未完成反思（未解锁）时，复制锁定
const copyLocked = computed(
  () =>
    !!props.message.hasReusableMaterial &&
    props.message.reflectState !== 'unlocked',
)

async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.message.content)
    copied.value = true
    antMessage.success('已复制到剪贴板')
    setTimeout(() => {
      copied.value = false
    }, 2000)
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

/** 环形进度条描边色，与 confidenceClass 保持一致 */
const confidenceColor = computed(() => {
  const c = props.message.confidence ?? 0
  if (c >= 0.8) return '#34D399'
  if (c >= 0.6) return '#FBBF24'
  return '#F87171'
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
  background: linear-gradient(135deg, #d4a373, #b8860b);
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
  color: #94a3b8;
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
    background: linear-gradient(135deg, rgba(212, 163, 115, 0.3), rgba(184, 134, 11, 0.15));
    color: #f8fafc;
    font-size: 14px;
    border-bottom-right-radius: 4px;
    word-break: break-word;
    white-space: pre-wrap;
    border: 1px solid rgba(212, 163, 115, 0.15);
  }

  &.ai-content {
    padding: 6px 0;
    font-size: 14px;
    color: #e2e8f0;
    word-break: break-word;
  }
}

/* ── Markdown 内容样式 (深色主题) ── */
.markdown-body {
  :deep(p) {
    margin: 0.4em 0;
  }

  :deep(h1),
  :deep(h2),
  :deep(h3),
  :deep(h4) {
    margin: 1em 0 0.4em;
    font-weight: 600;
    color: #f8fafc;
  }

  :deep(h1) {
    font-size: 1.4em;
  }
  :deep(h2) {
    font-size: 1.2em;
  }
  :deep(h3) {
    font-size: 1.05em;
  }

  :deep(code) {
    padding: 2px 6px;
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.08);
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.88em;
    color: #fbbf24;
  }

  :deep(pre) {
    margin: 12px 0;
    padding: 16px 18px;
    border-radius: 10px;
    background: rgba(0, 0, 0, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.06);
    overflow-x: auto;

    code {
      padding: 0;
      background: none;
      color: #e2e8f0;
      font-size: 13px;
      line-height: 1.65;
    }
  }

  :deep(blockquote) {
    margin: 8px 0;
    padding: 10px 16px;
    border-left: 3px solid #d4a373;
    background: rgba(212, 163, 115, 0.06);
    border-radius: 0 8px 8px 0;
    color: #94a3b8;
    font-style: italic;
  }

  :deep(ul),
  :deep(ol) {
    padding-left: 1.4em;
    margin: 0.4em 0;
  }

  :deep(li) {
    margin: 2px 0;
  }

  :deep(a) {
    color: #4a6cf7;
    text-decoration: none;
    &:hover {
      text-decoration: underline;
      color: #00d4ff;
    }
  }

  :deep(table) {
    margin: 12px 0;
    border-collapse: collapse;
    width: 100%;
    font-size: 13px;

    th,
    td {
      padding: 8px 12px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      text-align: left;
    }

    th {
      background: rgba(255, 255, 255, 0.05);
      color: #f8fafc;
      font-weight: 600;
    }

    td {
      color: #cbd5e1;
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
  color: #d4a373;
  font-weight: 400;
}

@keyframes blink {
  0%,
  50% {
    opacity: 1;
  }
  51%,
  100% {
    opacity: 0;
  }
}

/* ── 置信度 ── */
.msg-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  font-size: 12px;
}

/* 置信度：环形进度条 + 百分比 */
.confidence-ring {
  display: inline-flex;
  align-items: center;
  gap: 6px;

  :deep(.ant-progress-circle) {
    line-height: 1;
  }

  .ring-num {
    font-size: 11px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
  }

  .ring-label {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    font-weight: 500;
  }

  &.confidence-high {
    color: #34d399;
    .ring-num {
      color: #34d399;
    }
  }

  &.confidence-medium {
    color: #fbbf24;
    .ring-num {
      color: #fbbf24;
    }
  }

  &.confidence-low {
    color: #f87171;
    .ring-num {
      color: #f87171;
    }
  }
}

/* ── 正文引用角标 ── */
.markdown-body :deep(.cite-mark) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  margin: 0 2px;
  padding: 0 4px;
  border-radius: 8px;
  background: rgba(79, 124, 255, 0.16);
  border: 1px solid rgba(79, 124, 255, 0.32);
  color: #7aa2ff;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  vertical-align: super;
  cursor: pointer;
  user-select: none;
  transition:
    background 0.18s,
    color 0.18s,
    transform 0.18s;

  &:hover {
    background: rgba(79, 124, 255, 0.32);
    color: #fff;
    transform: translateY(-1px);
  }
}

/* Popover 定位锚点（零尺寸，仅用于锚定气泡） */
.ai-content {
  position: relative;
}

.markdown-body {
  position: relative;
}

.cite-anchor {
  position: absolute;
  width: 0;
  height: 0;
  pointer-events: none;
}

/* Popover 内容 */
.cite-pop {
  max-width: 320px;

  .cite-pop-head {
    display: flex;
    align-items: baseline;
    gap: 6px;
    margin-bottom: 4px;
  }

  .cite-pop-ref {
    flex-shrink: 0;
    padding: 1px 6px;
    border-radius: 8px;
    background: rgba(79, 124, 255, 0.18);
    color: #7aa2ff;
    font-size: 11px;
    font-weight: 700;
  }

  .cite-pop-doc {
    color: #e2e8f0;
    font-size: 13px;
    font-weight: 600;
    word-break: break-all;
  }

  .cite-pop-sub {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 6px;
    color: #94a3b8;
    font-size: 11px;
  }

  .cite-pop-score {
    color: #7aa2ff;
    font-weight: 600;
  }

  .cite-pop-text {
    margin: 0;
    color: #cbd5e1;
    font-size: 12px;
    line-height: 1.65;
    white-space: pre-wrap;
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
  color: #64748b;
  margin-bottom: 8px;
}

/* ── 操作按钮 ── */
.msg-actions {
  margin-top: 8px;
  opacity: 0;
  transition: opacity 0.2s;

  :deep(.ant-btn-text) {
    color: #64748b;
    &:hover {
      color: #d4a373;
    }
  }
}
</style>

<!-- Popover 通过 teleport 渲染，样式需非 scoped -->
<style lang="less">
.cite-popover {
  .ant-popover-inner {
    background: rgba(20, 27, 43, 0.97);
    border: 1px solid rgba(79, 124, 255, 0.28);
    border-radius: 10px;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45);
  }

  .ant-popover-inner-content {
    padding: 10px 12px;
  }

  .ant-popover-arrow-content::before,
  .ant-popover-arrow::before {
    background: rgba(20, 27, 43, 0.97);
  }
}
</style>
