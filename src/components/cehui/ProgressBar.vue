<script setup lang="ts">
/**
 * ProgressBar — 答题进度条组件
 *
 * 显示当前答题进度（第 N 题 / 共 M 题）
 */
import { computed } from 'vue'

const props = defineProps<{
  current: number
  total: number
}>()

const percent = computed(() => {
  if (props.total <= 0) return 0
  return Math.round((props.current / props.total) * 100)
})
</script>

<template>
  <div class="progress-bar">
    <div class="progress-bar__info">
      <span class="progress-bar__label">答题进度</span>
      <span class="progress-bar__count">{{ current }} / {{ total }}</span>
    </div>
    <div class="progress-bar__track">
      <div class="progress-bar__fill" :style="{ width: `${percent}%` }" />
    </div>
  </div>
</template>

<style scoped>
.progress-bar {
  width: 100%;
}

.progress-bar__info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.progress-bar__label {
  font-size: 13px;
  color: #94a3b8;
}

.progress-bar__count {
  font-size: 13px;
  color: #f8fafc;
  font-weight: 600;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.progress-bar__track {
  width: 100%;
  height: 6px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar__fill {
  height: 100%;
  background: linear-gradient(90deg, #d4a373, #4a6cf7);
  border-radius: 3px;
  transition: width 400ms cubic-bezier(0.4, 0, 0.2, 1);
}
</style>
