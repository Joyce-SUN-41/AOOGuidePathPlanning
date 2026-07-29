<template>
  <div class="chat-input-area">
    <div class="input-actions-row">
      <slot name="before" />
      <div class="input-actions-right">
        <a-button
          type="text"
          size="small"
          :disabled="!props.hasContent"
          @click="$emit('clear')"
          title="清空对话"
        >
          <template #icon><DeleteOutlined /></template>
        </a-button>
        <a-button
          type="text"
          size="small"
          :disabled="!props.hasContent"
          @click="$emit('export')"
          title="导出对话"
        >
          <template #icon><DownloadOutlined /></template>
        </a-button>
      </div>
    </div>

    <div class="input-row">
      <a-textarea
        ref="textareaRef"
        v-model:value="localInput"
        :auto-size="{ minRows: 1, maxRows: 6 }"
        :placeholder="placeholder"
        :disabled="props.sending"
        :bordered="false"
        class="chat-textarea"
        @press-enter="handleEnter"
      />
      <a-button
        type="primary"
        shape="circle"
        :loading="props.sending"
        :disabled="!canSubmit"
        class="send-btn"
        @click="handleSend"
      >
        <template #icon>
          <SendOutlined v-if="!props.sending" />
        </template>
      </a-button>
    </div>

    <div class="input-hint">
      <span v-if="props.sending" class="hint-thinking">
        <span class="hint-dot" />
        正在思考中...
      </span>
      <span v-else>{{ hintText }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  SendOutlined,
  DeleteOutlined,
  DownloadOutlined,
} from '@ant-design/icons-vue'

const props = withDefaults(defineProps<{
  modelValue?: string
  sending?: boolean
  hasContent?: boolean
  placeholder?: string
  hintType?: 'subject' | 'chinese' | 'mixed'
}>(), {
  placeholder: '输入你的问题，Enter 发送，Shift+Enter 换行',
  hintType: 'mixed',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
  clear: []
  export: []
  'quick-fill': [text: string]
}>()

const localInput = ref(props.modelValue || '')
const textareaRef = ref()

watch(() => props.modelValue, (val) => {
  localInput.value = val || ''
})

watch(localInput, (val) => {
  emit('update:modelValue', val)
})

const canSubmit = computed(() => {
  return localInput.value.trim().length > 0 && !props.sending
})

const hintText = computed(() => {
  if (props.hintType === 'chinese') return 'Enter 发送 · Shift+Enter 换行 · 基于学科知识库回答'
  return 'Enter 发送 · Shift+Enter 换行 · 基于 RAG 知识库增强回答'
})

function handleEnter(e: KeyboardEvent) {
  if (e.shiftKey) return
  e.preventDefault()
  if (canSubmit.value) {
    handleSend()
  }
}

function handleSend() {
  if (!canSubmit.value) return
  emit('send')
  setTimeout(() => {
    if (textareaRef.value) {
      const el = textareaRef.value.$el?.querySelector('textarea')
      if (el) el.style.height = ''
    }
  }, 50)
}
</script>

<style scoped lang="less">
.chat-input-area {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding: 10px 18px 12px;
}

.input-actions-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  min-height: 28px;
}

.input-actions-right {
  display: flex;
  gap: 2px;
  margin-left: auto;

  :deep(.ant-btn-text) {
    color: #475569 !important;
    &:hover:not(:disabled) { color: #94A3B8 !important; }
    &:disabled { color: rgba(71, 85, 105, 0.3) !important; }
  }
}

.input-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 14px;
  padding: 6px 6px 6px 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  transition: border-color 0.25s, box-shadow 0.25s;

  &:focus-within {
    border-color: rgba(212, 163, 115, 0.35);
    box-shadow: 0 0 0 3px rgba(212, 163, 115, 0.06);
    background: rgba(255, 255, 255, 0.06);
  }
}

.chat-textarea {
  flex: 1;
  font-size: 14px;
  line-height: 1.55;
  resize: none;
  background: transparent !important;

  :deep(textarea) {
    background: transparent !important;
    padding: 6px 0;
    color: #F8FAFC;

    &::placeholder {
      color: #475569;
    }
  }
}

.send-btn {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  min-width: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #D4A373, #B8860B) !important;
  border: none !important;
  box-shadow: 0 2px 12px rgba(212, 163, 115, 0.3);
  transition: all 0.25s;
  color: #0A0D14;

  &:hover:not(:disabled) {
    transform: scale(1.06);
    box-shadow: 0 4px 20px rgba(212, 163, 115, 0.45);
  }

  &:active:not(:disabled) {
    transform: scale(0.95);
  }

  &:disabled {
    background: rgba(255, 255, 255, 0.06) !important;
    color: rgba(100, 116, 139, 0.4) !important;
    box-shadow: none;
  }
}

.input-hint {
  margin-top: 8px;
  text-align: center;
  font-size: 11px;
  color: #475569;
}

.hint-thinking {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #D4A373;
}

.hint-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #D4A373;
  animation: dotPulse 1.2s ease-in-out infinite;
}

@keyframes dotPulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}
</style>
