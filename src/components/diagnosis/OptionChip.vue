<script setup lang="ts">
/**
 * OptionChip — 诊断选项芯片组件
 *
 * 可点击的选项按钮，支持选中、正确、错误等状态。
 */
import { computed } from 'vue'
import { CheckCircleFilled, CloseCircleFilled } from '@ant-design/icons-vue'
import type { DiagnosisOption } from '@/types'

const props = defineProps<{
  option: DiagnosisOption
  disabled?: boolean
  selected?: boolean
  /** 选项状态 */
  state?: 'default' | 'correct' | 'wrong' | 'selected'
}>()

const emit = defineEmits<{
  select: [optionId: string]
}>()

const classList = computed(() => ({
  'option-chip': true,
  'option-chip--disabled': props.disabled,
  'option-chip--selected': props.selected,
  'option-chip--correct': props.state === 'correct',
  'option-chip--wrong': props.state === 'wrong'
}))

function handleClick() {
  if (!props.disabled) {
    emit('select', props.option.id)
  }
}
</script>

<template>
  <button :class="classList" :disabled="disabled" type="button" @click="handleClick">
    <span class="option-chip__label">{{ option.id.toUpperCase() }}</span>
    <span class="option-chip__text">{{ option.text }}</span>

    <CheckCircleFilled
      v-if="state === 'correct'"
      class="option-chip__icon option-chip__icon--correct"
    />
    <CloseCircleFilled
      v-else-if="state === 'wrong'"
      class="option-chip__icon option-chip__icon--wrong"
    />
  </button>
</template>

<style scoped>
.option-chip {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  color: #cbd5e1;
  font-size: 14px;
  cursor: pointer;
  transition: all 200ms ease;
  text-align: left;
}

.option-chip:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(212, 163, 115, 0.3);
}

.option-chip--selected {
  background: rgba(212, 163, 115, 0.1);
  border-color: rgba(212, 163, 115, 0.35);
  color: #f8fafc;
}

.option-chip--correct {
  background: rgba(82, 196, 26, 0.1);
  border-color: rgba(82, 196, 26, 0.35);
  color: #73d13d;
}

.option-chip--wrong {
  background: rgba(255, 77, 79, 0.1);
  border-color: rgba(255, 77, 79, 0.35);
  color: #ff7875;
}

.option-chip--disabled {
  cursor: default;
}

.option-chip__label {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.option-chip--selected .option-chip__label {
  background: rgba(212, 163, 115, 0.25);
  color: #d4a373;
}

.option-chip--correct .option-chip__label {
  background: rgba(82, 196, 26, 0.25);
  color: #73d13d;
}

.option-chip--wrong .option-chip__label {
  background: rgba(255, 77, 79, 0.25);
  color: #ff7875;
}

.option-chip__text {
  flex: 1;
}

.option-chip__icon {
  font-size: 18px;
  flex-shrink: 0;
}

.option-chip__icon--correct {
  color: #52c41a;
}
.option-chip__icon--wrong {
  color: #ff4d4f;
}
</style>
