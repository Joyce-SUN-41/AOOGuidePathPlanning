<script setup lang="ts">
/**
 * DiagnosisRadar — 诊断结果雷达图组件
 *
 * 使用 ECharts 渲染掌握度雷达图，支持暗色主题。
 */
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { MasteryItem } from '@/types'

const props = defineProps<{
  data: MasteryItem[]
  height?: number
}>()

const emit = defineEmits<{
  ready: [chart: echarts.ECharts]
}>()

const containerRef = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

function render() {
  if (!chart || !props.data.length) return

  const indicators = props.data.map((item) => ({
    name:
      item.knowledgePoint.length > 6
        ? item.knowledgePoint.slice(0, 6) + '...'
        : item.knowledgePoint,
    max: 1
  }))

  const values = props.data.map((item) => item.mastery)

  chart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(10,13,20,0.95)',
      borderColor: 'rgba(212,163,115,0.2)',
      textStyle: { color: '#F8FAFC', fontSize: 13 }
    },
    radar: {
      indicator: indicators,
      center: ['50%', '52%'],
      radius: '62%',
      axisName: {
        color: '#94A3B8',
        fontSize: 12
      },
      splitArea: {
        areaStyle: {
          color: ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.02)']
        }
      },
      splitLine: {
        lineStyle: { color: 'rgba(255,255,255,0.08)' }
      },
      axisLine: {
        lineStyle: { color: 'rgba(255,255,255,0.1)' }
      }
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: values,
            name: '掌握度',
            areaStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: 'rgba(212,163,115,0.3)' },
                { offset: 1, color: 'rgba(212,163,115,0.05)' }
              ])
            },
            lineStyle: { color: '#D4A373', width: 2 },
            itemStyle: { color: '#D4A373' },
            symbol: 'circle',
            symbolSize: 6
          }
        ]
      }
    ]
  })
}

onMounted(() => {
  nextTick(() => {
    if (!containerRef.value) return
    chart = echarts.init(containerRef.value, undefined, {
      devicePixelRatio: Math.min(window.devicePixelRatio || 1, 2)
    })
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(containerRef.value)
    render()
    emit('ready', chart)
  })
})

watch(() => props.data, render, { deep: true })

onUnmounted(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="containerRef" class="diagnosis-radar" :style="{ height: `${height ?? 340}px` }" />
</template>

<style scoped>
.diagnosis-radar {
  width: 100%;
  min-height: 280px;
}
</style>
