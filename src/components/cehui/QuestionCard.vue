<script setup lang="ts">
/**
 * QuestionCard — 测绘题目卡片组件
 *
 * 展示单个测绘题目，支持选项选择、反馈展示。
 * 从 CehuiView 中独立抽取。
 */
import { computed } from 'vue'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined
} from '@ant-design/icons-vue'
import OptionChip from './OptionChip.vue'
import type { CehuiQuestion, CehuiOption } from '@/types'

const props = defineProps<{
  /** 当前题目 */
  question: CehuiQuestion
  /** 题目序号 (1-based) */
  index: number
  /** 总题数 */
  total: number
  /** 当前选中的选项 ID */
  selectedOptionId: string | null
  /** 是否显示反馈 */
  showFeedback: boolean
  /** 当前答题是否正确 */
  isCorrect: boolean
  /** 答题耗时(秒) */
  elapsed?: number
}>()

const emit = defineEmits<{
  select: [optionId: string]
}>()

const difficultyColor = computed(() => {
  const map: Record<number, string> = { 1: 'green', 2: 'cyan', 3: 'blue', 4: 'orange', 5: 'red' }
  return map[props.question.difficulty] ?? 'default'
})

const difficultyLabel = computed(() => {
  const map: Record<number, string> = { 1: '基础', 2: '简单', 3: '中等', 4: '较难', 5: '困难' }
  return map[props.question.difficulty] ?? '未知'
})

function getOptionStyle(option: CehuiOption): 'default' | 'correct' | 'wrong' | 'selected' {
  if (!props.showFeedback) return 'default'
  if (option.weight === 1) return 'correct'
  if (option.id === props.selectedOptionId && option.weight !== 1) return 'wrong'
  return 'default'
}
</script>

<template>
  <div class="question-card">
    <!-- 题头：序号 + 难度标签 -->
    <div class="qc-header">
      <span class="qc-index"> 第 {{ index }}/{{ total }} 题 </span>
      <a-tag :color="difficultyColor" class="qc-difficulty">
        {{ difficultyLabel }}
      </a-tag>
      <span v-if="showFeedback && elapsed !== undefined" class="qc-elapsed">
        <ClockCircleOutlined /> {{ elapsed.toFixed(1) }}s
      </span>
    </div>

    <!-- 题干 -->
    <h3 class="qc-title">{{ question.title }}</h3>

    <!-- 选项列表 -->
    <div class="qc-options">
      <OptionChip
        v-for="option in question.options"
        :key="option.id"
        :option="option"
        :disabled="showFeedback"
        :selected="selectedOptionId === option.id"
        :state="getOptionStyle(option)"
        @select="emit('select', option.id)"
      />
    </div>

    <!-- 反馈区域 -->
    <div
      v-if="showFeedback"
      class="qc-feedback"
      :class="{ 'qc-feedback--correct': isCorrect, 'qc-feedback--wrong': !isCorrect }"
    >
      <CheckCircleOutlined v-if="isCorrect" class="qc-feedback-icon" />
      <CloseCircleOutlined v-else class="qc-feedback-icon" />
      <span>{{ isCorrect ? '回答正确！' : '回答错误，请查看正确答案' }}</span>
    </div>
  </div>
</template>

<style scoped>
.question-card {
  padding: 20px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
}

.qc-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.qc-index {
  font-size: 13px;
  color: #94a3b8;
  font-weight: 500;
}

.qc-difficulty {
  font-size: 12px;
}

.qc-elapsed {
  margin-left: auto;
  font-size: 12px;
  color: #64748b;
  display: flex;
  align-items: center;
  gap: 4px;
}

.qc-title {
  font-size: 16px;
  font-weight: 600;
  color: #f8fafc;
  margin: 0 0 20px;
  line-height: 1.6;
}

.qc-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.qc-feedback {
  margin-top: 16px;
  padding: 12px 16px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
}

.qc-feedback--correct {
  background: rgba(82, 196, 26, 0.1);
  border: 1px solid rgba(82, 196, 26, 0.25);
  color: #73d13d;
}

.qc-feedback--wrong {
  background: rgba(255, 77, 79, 0.1);
  border: 1px solid rgba(255, 77, 79, 0.25);
  color: #ff7875;
}

.qc-feedback-icon {
  font-size: 16px;
}
</style>
