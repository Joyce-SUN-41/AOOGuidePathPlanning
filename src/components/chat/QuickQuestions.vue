<template>
  <div class="quick-questions" v-if="questions.length > 0">
    <div class="qq-label">试试这些问题</div>
    <div class="qq-grid">
      <div v-for="q in questions" :key="q.id" class="qq-item" @click="$emit('select', q.text)">
        <component v-if="q.icon" :is="iconMap[q.icon]" class="qq-icon" />
        <span>{{ q.text }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  BulbOutlined,
  QuestionCircleOutlined,
  ExperimentOutlined,
  BookOutlined,
  ThunderboltOutlined
} from '@ant-design/icons-vue'
import type { QuickQuestion } from '@/types/rag'
import type { Component } from 'vue'

defineProps<{
  questions: QuickQuestion[]
}>()

defineEmits<{
  select: [text: string]
}>()

const iconMap: Record<string, Component> = {
  bulb: BulbOutlined,
  question: QuestionCircleOutlined,
  experiment: ExperimentOutlined,
  book: BookOutlined,
  thunderbolt: ThunderboltOutlined
}
</script>

<style scoped lang="less">
.quick-questions {
  padding: 14px 20px 6px;
}

.qq-label {
  font-size: 11px;
  color: #475569;
  margin-bottom: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.qq-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.qq-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border-radius: 20px;
  background: rgba(212, 163, 115, 0.08);
  color: #d4a373;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.25s ease;
  border: 1px solid rgba(212, 163, 115, 0.12);
  user-select: none;

  &:hover {
    background: rgba(212, 163, 115, 0.16);
    border-color: rgba(212, 163, 115, 0.3);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(212, 163, 115, 0.1);
  }

  &:active {
    transform: translateY(0);
    background: rgba(212, 163, 115, 0.2);
  }
}

.qq-icon {
  font-size: 14px;
  flex-shrink: 0;
}
</style>
