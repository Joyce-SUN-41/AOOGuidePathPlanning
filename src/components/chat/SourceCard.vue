<template>
  <div class="source-card" :class="{ expanded }">
    <div class="source-header" @click="toggle">
      <div class="source-badge">
        <TagOutlined />
        <span class="source-ref">[{{ source.ref }}]</span>
      </div>
      <span class="source-doc">{{ source.document }}</span>
      <span v-if="source.page" class="source-page">p.{{ source.page }}</span>
      <span class="source-score">{{ (source.score * 100).toFixed(0) }}%</span>
      <DownOutlined class="source-arrow" />
    </div>
    <transition name="source-expand">
      <div v-if="expanded" class="source-body">
        <div v-if="source.section" class="source-section">{{ source.section }}</div>
        <div class="source-text">{{ source.content }}</div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { TagOutlined, DownOutlined } from '@ant-design/icons-vue'
import type { RAGSource } from '@/types/rag'

const { source } = defineProps<{
  source: RAGSource
}>()

const expanded = ref(false)

function toggle() {
  expanded.value = !expanded.value
}
</script>

<style scoped lang="less">
.source-card {
  margin-top: 6px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  background: #fafbfc;
  overflow: hidden;
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
  cursor: pointer;

  &:hover {
    border-color: #d0d5ff;
    box-shadow: 0 1px 4px rgba(79, 124, 255, 0.08);
  }

  &.expanded {
    border-color: #b8cbff;
    background: #f5f7ff;
  }
}

.source-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 12px;
  color: #5c5a57;
  user-select: none;
}

.source-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 12px;
  background: rgba(79, 124, 255, 0.1);
  color: #4f7cff;
  font-size: 11px;
  font-weight: 600;
}

.source-doc {
  flex: 1;
  font-weight: 500;
  color: #e2e8f0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-page {
  color: #94a3b8;
  font-size: 11px;
}

.source-score {
  padding: 1px 6px;
  border-radius: 4px;
  background: #eff3ff;
  color: #3b5fd9;
  font-size: 11px;
  font-weight: 600;
}

.source-arrow {
  font-size: 10px;
  color: #a8a6a2;
  transition: transform 0.2s;

  .expanded & {
    transform: rotate(180deg);
  }
}

.source-body {
  padding: 0 12px 10px;
  border-top: 1px solid #e8e8e8;
  padding-top: 8px;
}

.source-section {
  font-size: 12px;
  font-weight: 600;
  color: #3d3b39;
  margin-bottom: 6px;
}

.source-text {
  font-size: 12px;
  line-height: 1.6;
  color: #5c5a57;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}

.source-expand-enter-active {
  transition: all 0.25s ease;
  overflow: hidden;
}

.source-expand-leave-active {
  transition: all 0.15s ease;
  overflow: hidden;
}

.source-expand-enter-from,
.source-expand-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}
</style>
