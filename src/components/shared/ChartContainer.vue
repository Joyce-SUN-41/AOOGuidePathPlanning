<script setup lang="ts">
/**
 * ChartContainer — 通用 ECharts 容器组件
 *
 * 自动处理：
 *   - ResizeObserver 自适应
 *   - 空数据占位
 *   - 加载状态
 *   - 错误状态
 *
 * 用法:
 *   <ChartContainer ref="chartRef" :height="400" @ready="onChartReady">
 *     <div ref="chartDom" />
 *   </ChartContainer>
 */
import { ref, onUnmounted, computed } from 'vue'
import type { EChartsType } from 'echarts'
import SkeletonLoading from './SkeletonLoading.vue'
import ErrorState from './ErrorState.vue'

const props = withDefaults(
  defineProps<{
    /** 图表高度 */
    height?: number | string
    /** 是否显示加载骨架 */
    loading?: boolean
    /** 错误信息 */
    error?: string
    /** 是否有空数据（控制空状态显示） */
    isEmpty?: boolean
    /** 空状态提示 */
    emptyText?: string
    /** 是否显示标题 */
    title?: string
    /** 标题图标组件 */
    titleIcon?: object
  }>(),
  {
    height: 360,
    loading: false,
    error: '',
    isEmpty: false,
    emptyText: '暂无数据',
    title: ''
  }
)

const emit = defineEmits<{
  ready: [chart: EChartsType]
  retry: []
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const chartInstance = ref<any>(null)

const heightStyle = computed(() => {
  if (typeof props.height === 'number') return `${props.height}px`
  return props.height
})

function setChart(chart: any) {
  chartInstance.value = chart
  emit('ready', chart)
}

function getInstance(): any {
  return chartInstance.value
}

defineExpose({ getInstance, setChart })

onUnmounted(() => {
  chartInstance.value?.dispose()
})
</script>

<template>
  <div class="chart-container" :style="{ '--chart-height': heightStyle }">
    <!-- Header -->
    <div v-if="title" class="chart-container__header">
      <component v-if="titleIcon" :is="titleIcon" class="chart-container__header-icon" />
      <span class="chart-container__header-title">{{ title }}</span>
    </div>

    <!-- Loading -->
    <SkeletonLoading v-if="loading" type="chart" :height="height" />

    <!-- Error -->
    <ErrorState v-else-if="error" :description="error" show-retry compact @retry="emit('retry')" />

    <!-- Empty -->
    <div v-else-if="isEmpty" class="chart-container__empty">
      <p>{{ emptyText }}</p>
    </div>

    <!-- Chart slot -->
    <div v-else ref="containerRef" class="chart-container__body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.chart-container {
  width: 100%;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  overflow: hidden;
}

.chart-container__header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 20px 0;
  font-size: 14px;
  font-weight: 600;
  color: #f8fafc;
}

.chart-container__header-icon {
  color: #d4a373;
  font-size: 16px;
}

.chart-container__body {
  width: 100%;
  height: var(--chart-height, 360px);
  min-height: 200px;
}

.chart-container__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--chart-height, 360px);
  min-height: 200px;
  color: #64748b;
  font-size: 14px;
}
</style>
