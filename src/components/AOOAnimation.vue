<script setup lang="ts">
/**
 * AOOAnimation.vue — AOO 寻优过程可视化动画组件
 *
 * 功能：
 *   - 散点图展示种群分布 (X=迭代, Y=适应度, 颜色编码个体角色)
 *   - 收敛曲线叠加 (最优/平均/中位数适应度曲线)
 *   - 种群多样性曲线 (右 Y 轴)
 *   - 播放控制 (播放/暂停/速度调节/进度拖拽)
 *   - 实时统计面板 (迭代数/最优适应度/平均适应度/多样性)
 *
 * 数据来源：父组件传入 AOOConvergenceData（与后端 app/schemas/aoo.py 同步）
 */
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import {
  PauseCircleOutlined,
  CaretRightOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
  ReloadOutlined,
  ThunderboltOutlined
} from '@ant-design/icons-vue'
import type { AOOConvergenceData } from '@/types/aoo'

// ═══════════ Props ═══════════
const props = withDefaults(
  defineProps<{
    /** AOO 收敛数据（全部迭代数据） */
    convergenceData: AOOConvergenceData
    /** 是否自动播放 */
    autoPlay?: boolean
    /** 图表高度（px） */
    height?: number
    /** 是否显示控制栏 */
    showControls?: boolean
    /** 是否显示统计面板 */
    showStats?: boolean
  }>(),
  {
    autoPlay: true,
    height: 480,
    showControls: true,
    showStats: true
  }
)

// ═══════════ Emits ═══════════
const emit = defineEmits<{
  (e: 'frameChange', iteration: number, bestFitness: number): void
  (e: 'complete'): void
  (e: 'playStateChange', playing: boolean): void
}>()

// ═══════════ 颜色常量（对齐品牌色板） ═══════════
const COLORS = {
  elite: '#FF4D4F', // 红色 — 精英个体
  normal: '#4F7CFF', // 蓝色 — 普通个体
  exploring: '#52C41A', // 绿色 — 探索中
  bestLine: '#FF4D4F', // 最优适应度曲线
  avgLine: '#4F7CFF', // 平均适应度曲线
  medianLine: '#B8A99A', // 中位数适应度曲线
  diversityLine: '#FA8C16', // 多样性曲线
  historyPoint: 'rgba(203, 213, 225, 0.3)', // 历史种群点（深色背景）
  progressTrack: 'rgba(255, 255, 255, 0.12)'
}

/** 角色 → 颜色映射 */
const ROLE_COLOR_MAP: Record<string, string> = {
  elite: COLORS.elite,
  normal: COLORS.normal,
  exploring: COLORS.exploring
}

// ═══════════ 速度档位 ═══════════
const SPEED_OPTIONS = [
  { label: '1x', value: 1, interval: 600 },
  { label: '2x', value: 2, interval: 300 },
  { label: '5x', value: 5, interval: 120 }
] as const

// ═══════════ 响应式状态 ═══════════
const chartContainer = ref<HTMLDivElement | null>(null)
let chartInstance: echarts.ECharts | null = null
let animationTimer: ReturnType<typeof setInterval> | null = null
let resizeObserver: ResizeObserver | null = null

/** 当前播放帧索引 (0-based) */
const currentFrameIndex = ref(0)
/** 是否正在播放 */
const isPlaying = ref(props.autoPlay)
/** 当前播放速度档位 */
const currentSpeed = ref<1 | 2 | 5>(1)
/** 是否已完成一轮播放 */
const hasCompleted = ref(false)

// ═══════════ 计算属性 ═══════════

/** 总帧数 */
const totalFrames = computed(() => props.convergenceData.iterations.length)

/** 当前迭代号 */
const currentIteration = computed(
  () => props.convergenceData.iterations[currentFrameIndex.value] ?? 0
)

/** 当前最优适应度 */
const currentBestFitness = computed(
  () => props.convergenceData.bestFitness[currentFrameIndex.value] ?? 0
)

/** 当前平均适应度 */
const currentAvgFitness = computed(
  () => props.convergenceData.avgFitness[currentFrameIndex.value] ?? 0
)

/** 当前种群多样性 */
const currentDiversity = computed(
  () => props.convergenceData.diversity[currentFrameIndex.value] ?? 0
)

/** 播放进度 (0-100) */
const progress = computed(() => {
  if (totalFrames.value <= 1) return 0
  return Math.round((currentFrameIndex.value / (totalFrames.value - 1)) * 100)
})

/** 当前帧间隔 (ms) */
const frameInterval = computed(() => {
  const opt = SPEED_OPTIONS.find((s) => s.value === currentSpeed.value)
  return opt?.interval ?? 600
})

/** 总迭代数 */
const totalIterations = computed(() => props.convergenceData.iterations[totalFrames.value - 1] ?? 0)

/** 当前帧四分位区间 (Q1~Q3)，反映种群集中程度 */
const currentQuartile = computed<{ q1: number; q3: number } | null>(() => {
  const q1 = props.convergenceData.q1Fitness?.[currentFrameIndex.value]
  const q3 = props.convergenceData.q3Fitness?.[currentFrameIndex.value]
  if (typeof q1 !== 'number' || typeof q3 !== 'number') return null
  return { q1, q3 }
})

/** 元信息 */
const metadata = computed(() => props.convergenceData.metadata)

/** 种群规模 */
const populationSize = computed(() => metadata.value?.populationSize ?? 0)

// ═══════════ ECharts 初始化 ═══════════

function initChart(): void {
  if (!chartContainer.value) return

  if (chartInstance) {
    chartInstance.dispose()
  }

  chartInstance = echarts.init(chartContainer.value, undefined, {
    devicePixelRatio: window.devicePixelRatio || 1
  })

  // 响应式缩放
  resizeObserver = new ResizeObserver(() => {
    chartInstance?.resize()
  })
  resizeObserver.observe(chartContainer.value)
}

/** 构建完整 ECharts 配置 */
function buildChartOption(): EChartsOption {
  const allIterations = props.convergenceData.iterations
  const bestFitness = props.convergenceData.bestFitness
  const avgFitness = props.convergenceData.avgFitness
  const medianFitness = props.convergenceData.medianFitness
  const diversity = props.convergenceData.diversity
  const snapshots = props.convergenceData.populationSnapshots
  const q1Fitness = props.convergenceData.q1Fitness
  const q3Fitness = props.convergenceData.q3Fitness

  const currentIdx = currentFrameIndex.value
  const maxIter = totalIterations.value

  // ── 构建历史种群散点数据（当前帧之前的所有迭代） ──
  const historyData: any[] = []
  // ── 构建当前帧种群散点数据 ──
  const currentData: any[] = []

  if (snapshots && snapshots.length > 0) {
    // 历史帧（已淡出）
    for (let i = 0; i < currentIdx; i++) {
      const snap = snapshots[i]
      if (!snap) continue
      const iter = allIterations[i]
      for (let j = 0; j < snap.fitnessValues.length; j++) {
        historyData.push({
          value: [iter, snap.fitnessValues[j]],
          symbolSize: 4
        })
      }
    }

    // 当前帧（全彩色 + 标记最优个体）
    const snap = snapshots[currentIdx]
    if (snap) {
      const iter = allIterations[currentIdx]
      for (let j = 0; j < snap.fitnessValues.length; j++) {
        const role = snap.colors[j] ?? 'normal'
        const isBest = j === snap.bestIndex
        currentData.push({
          value: [iter, snap.fitnessValues[j]],
          symbolSize: isBest ? 12 : 7,
          itemStyle: {
            color: ROLE_COLOR_MAP[role] ?? COLORS.normal,
            borderColor: isBest ? '#fff' : 'transparent',
            borderWidth: isBest ? 2 : 0,
            shadowBlur: isBest ? 8 : 0,
            shadowColor: isBest ? ROLE_COLOR_MAP[role] : 'transparent'
          }
        })
      }
    }
  }

  // ── 折线数据：仅显示到当前帧 ──
  const lineDataLength = currentIdx + 1
  const lineBestData: [number, number][] = []
  const lineAvgData: [number, number][] = []
  const lineMedianData: [number, number][] = []
  const lineDiversityData: [number, number][] = []

  // 四分位误差带：Q1 作为透明基线，band 高度 = Q3 - Q1（stack 叠加实现区间填充）
  const hasQuartile =
    Array.isArray(q1Fitness) &&
    Array.isArray(q3Fitness) &&
    q1Fitness.length > 0 &&
    q3Fitness.length >= q1Fitness.length
  const bandLowerData: [number, number][] = []
  const bandRangeData: [number, number][] = []

  for (let i = 0; i < lineDataLength; i++) {
    lineBestData.push([allIterations[i]!, bestFitness[i]!] as [number, number])
    lineAvgData.push([allIterations[i]!, avgFitness[i]!] as [number, number])
    lineMedianData.push([allIterations[i]!, medianFitness[i]!] as [number, number])
    lineDiversityData.push([allIterations[i]!, diversity[i]!] as [number, number])

    if (hasQuartile) {
      const q1 = q1Fitness![i]
      const q3 = q3Fitness![i]
      if (typeof q1 === 'number' && typeof q3 === 'number') {
        bandLowerData.push([allIterations[i]!, q1] as [number, number])
        bandRangeData.push([allIterations[i]!, Math.max(0, q3 - q1)] as [number, number])
      }
    }
  }

  // ── 当前迭代标记线 ──
  const currentIter = currentIteration.value
  const markLineData: echarts.MarkLineComponentOption['data'] = []
  if (currentIter > 0) {
    markLineData.push({
      xAxis: currentIter,
      label: { show: true, formatter: `第 ${currentIter} 代`, fontSize: 11, color: '#CBD5E1' },
      lineStyle: { color: 'rgba(212, 163, 115, 0.7)', type: 'dashed', width: 1.5, opacity: 0.8 }
    })
  }

  return {
    animation: true,
    animationDuration: 400,
    animationEasing: 'cubicInOut' as const,

    tooltip: {
      trigger: 'item' as const,
      backgroundColor: 'rgba(20, 27, 43, 0.95)',
      borderColor: 'rgba(212, 163, 115, 0.35)',
      borderWidth: 1,
      textStyle: { color: '#F8FAFC', fontSize: 12 },
      formatter: (params: any) => {
        if (!params.value || params.value.length < 2) return ''
        const [iter, fitness] = params.value
        if (params.seriesName === '历史种群' || params.seriesName === '当前种群') {
          return `迭代: ${iter}<br/>适应度: ${fitness.toFixed(4)}`
        }
        if (params.seriesName === '种群多样性') {
          return `迭代: ${iter}<br/>多样性: ${(fitness * 100).toFixed(1)}%`
        }
        return `迭代: ${iter}<br/>适应度: ${fitness.toFixed(4)}`
      }
    } as any,

    legend: {
      bottom: 8,
      left: 'center',
      textStyle: { color: '#94A3B8', fontSize: 12 },
      itemWidth: 14,
      itemHeight: 8,
      itemGap: 20,
      // 'Q1 基线' 为技术性占位序列，不进入图例
      data: [
        '四分位区间',
        '历史种群',
        '当前种群',
        '最优适应度',
        '平均适应度',
        '中位数适应度',
        '种群多样性'
      ],
      selected: {
        历史种群: !!(snapshots && snapshots.length > 0),
        四分位区间: hasQuartile,
        中位数适应度: false // 默认隐藏减少视觉噪音
      }
    },

    grid: {
      top: 24,
      right: 72,
      bottom: 48,
      left: 64,
      containLabel: false
    },

    xAxis: {
      type: 'value' as const,
      name: '迭代次数',
      nameLocation: 'middle',
      nameGap: 30,
      nameTextStyle: { color: '#CBD5E1', fontSize: 12, fontWeight: 500 },
      min: 1,
      max: maxIter,
      axisLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.35)' } },
      axisTick: { show: false },
      axisLabel: { color: '#94A3B8', fontSize: 11 },
      splitLine: { show: true, lineStyle: { color: 'rgba(148, 163, 184, 0.08)' } }
    },

    yAxis: [
      {
        type: 'value' as const,
        name: '适应度',
        nameLocation: 'middle',
        nameGap: 48,
        nameTextStyle: { color: '#CBD5E1', fontSize: 12, fontWeight: 500 },
        min: (value: { min: number }) => Math.max(0, Math.floor(value.min * 10) / 10 - 0.05),
        max: (value: { max: number }) => Math.min(1, Math.ceil(value.max * 10) / 10 + 0.05),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: '#94A3B8',
          fontSize: 11,
          formatter: (val: number) => val.toFixed(2)
        },
        splitLine: { show: true, lineStyle: { color: 'rgba(148, 163, 184, 0.08)' } }
      },
      {
        type: 'value' as const,
        name: '多样性',
        nameLocation: 'middle',
        nameGap: 48,
        nameTextStyle: { color: '#CBD5E1', fontSize: 12, fontWeight: 500 },
        min: 0,
        max: 1,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: '#94A3B8',
          fontSize: 11,
          formatter: (val: number) => `${(val * 100).toFixed(0)}%`
        },
        splitLine: { show: false }
      }
    ],

    series: [
      // ⓪-a 四分位误差带下界 Q1（透明占位，仅用于抬高 stack 基线）
      {
        name: 'Q1 基线',
        type: 'line' as const,
        yAxisIndex: 0,
        stack: 'quartile-band',
        data: bandLowerData,
        smooth: true,
        symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: { opacity: 0 },
        silent: true,
        tooltip: { show: false },
        zlevel: 0,
        animation: false
      },

      // ⓪-b 四分位误差带 Q1~Q3（种群集中区间）
      {
        name: '四分位区间',
        type: 'line' as const,
        yAxisIndex: 0,
        stack: 'quartile-band',
        data: bandRangeData,
        smooth: true,
        symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(0, 212, 255, 0.1)' },
        silent: true,
        tooltip: { show: false },
        zlevel: 0,
        animation: false
      },

      // ① 历史种群散点（半透明灰点 — 显示收敛轨迹）
      {
        name: '历史种群',
        type: 'scatter' as const,
        yAxisIndex: 0,
        data: historyData,
        symbolSize: 4,
        itemStyle: { color: COLORS.historyPoint },
        emphasis: { scale: 1.2 },
        zlevel: 0,
        animation: false // 历史点不需要入场动画
      },

      // ② 当前帧种群散点（彩色 — 精英红 / 普通蓝 / 探索绿）
      {
        name: '当前种群',
        type: 'scatter' as const,
        yAxisIndex: 0,
        data: currentData,
        emphasis: { scale: 1.5 },
        zlevel: 2,
        markLine: {
          silent: true,
          symbol: 'none',
          data: markLineData,
          zlevel: 1
        }
      },

      // ③ 最优适应度收敛曲线
      {
        name: '最优适应度',
        type: 'line' as const,
        yAxisIndex: 0,
        data: lineBestData,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: COLORS.bestLine, width: 2.5 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(255, 77, 79, 0.12)' },
            { offset: 1, color: 'rgba(255, 77, 79, 0.01)' }
          ])
        },
        zlevel: 1
      },

      // ④ 平均适应度曲线
      {
        name: '平均适应度',
        type: 'line' as const,
        yAxisIndex: 0,
        data: lineAvgData,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: COLORS.avgLine, width: 2, type: 'dashed' },
        zlevel: 1
      },

      // ⑤ 中位数适应度曲线（轻量辅助线）
      {
        name: '中位数适应度',
        type: 'line' as const,
        yAxisIndex: 0,
        data: lineMedianData,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: COLORS.medianLine, width: 1.2, type: 'dotted' },
        zlevel: 0
      },

      // ⑥ 种群多样性曲线（右 Y 轴）
      {
        name: '种群多样性',
        type: 'line' as const,
        yAxisIndex: 1,
        data: lineDiversityData,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: COLORS.diversityLine, width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(250, 140, 22, 0.15)' },
            { offset: 1, color: 'rgba(250, 140, 22, 0.02)' }
          ])
        },
        zlevel: 1
      }
    ]
  }
}

/** 更新图表渲染 */
function updateChart(): void {
  if (!chartInstance) return
  const option = buildChartOption()
  chartInstance.setOption(option, { notMerge: true, lazyUpdate: false })
}

// ═══════════ 动画控制 ═══════════

/** 跳转到指定帧 */
function seekTo(frameIndex: number): void {
  const clamped = Math.max(0, Math.min(frameIndex, totalFrames.value - 1))
  if (clamped === currentFrameIndex.value) return

  currentFrameIndex.value = clamped
  updateChart()

  emit('frameChange', currentIteration.value, currentBestFitness.value)

  // 到达末尾
  if (clamped >= totalFrames.value - 1) {
    hasCompleted.value = true
    if (isPlaying.value) {
      pause()
      emit('complete')
      emit('playStateChange', false)
    }
  }
}

/** 前进一帧 */
function stepForward(): void {
  seekTo(currentFrameIndex.value + 1)
}

/** 后退一帧 */
function stepBackward(): void {
  seekTo(currentFrameIndex.value - 1)
}

/** 开始播放 */
function play(): void {
  if (isPlaying.value) return
  if (hasCompleted.value) {
    // 已完成则从头开始
    hasCompleted.value = false
    currentFrameIndex.value = 0
    updateChart()
  }
  isPlaying.value = true
  emit('playStateChange', true)
  startAnimationTimer()
}

/** 暂停播放 */
function pause(): void {
  if (!isPlaying.value) return
  isPlaying.value = false
  emit('playStateChange', false)
  stopAnimationTimer()
}

/** 切换播放/暂停 */
function togglePlayPause(): void {
  if (isPlaying.value) {
    pause()
  } else {
    play()
  }
}

/** 设置播放速度 */
function setSpeed(speed: 1 | 2 | 5): void {
  currentSpeed.value = speed
  if (isPlaying.value) {
    // 重启定时器以应用新速度
    stopAnimationTimer()
    startAnimationTimer()
  }
}

/** 从头播放 */
function replay(): void {
  hasCompleted.value = false
  seekTo(0)
  play()
}

/** 启动动画定时器 */
function startAnimationTimer(): void {
  stopAnimationTimer()
  animationTimer = setInterval(() => {
    if (currentFrameIndex.value >= totalFrames.value - 1) {
      pause()
      hasCompleted.value = true
      emit('complete')
      return
    }
    // 逐帧前进
    currentFrameIndex.value++
    updateChart()
    emit('frameChange', currentIteration.value, currentBestFitness.value)
  }, frameInterval.value)
}

/** 停止动画定时器 */
function stopAnimationTimer(): void {
  if (animationTimer) {
    clearInterval(animationTimer)
    animationTimer = null
  }
}

// ═══════════ 数据变更监听 ═══════════

/**
 * 监听 convergenceData 变化 — 当新数据到达时重置动画
 * 使用 immediate 确保首次渲染
 */
watch(
  () => props.convergenceData,
  (newData, _oldData) => {
    if (!newData || newData.iterations.length === 0) return

    // 重置状态
    stopAnimationTimer()
    currentFrameIndex.value = 0
    hasCompleted.value = false

    // 确保图表已初始化
    nextTick(() => {
      if (!chartInstance) initChart()
      updateChart()

      // 自动播放
      if (props.autoPlay) {
        isPlaying.value = true
        startAnimationTimer()
      }
    })
  },
  { immediate: true, deep: false }
)

// ═══════════ 响应式中断处理 ═══════════

// 窗口失焦时暂停（避免后台消耗性能）
function handleVisibilityChange(): void {
  if (document.hidden && isPlaying.value) {
    pause()
  }
}

// ═══════════ 生命周期 ═══════════

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)

  // 首次渲染可能在 watch immediate 中已处理，这里做兜底
  nextTick(() => {
    if (props.convergenceData.iterations.length > 0 && !chartInstance) {
      initChart()
      updateChart()
      if (props.autoPlay) {
        isPlaying.value = true
        startAnimationTimer()
      }
    }
  })
})

onUnmounted(() => {
  stopAnimationTimer()
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})

// ═══════════ 暴露方法（父组件通过 ref 调用） ═══════════
defineExpose({
  play,
  pause,
  togglePlayPause,
  seekTo,
  replay,
  stepForward,
  stepBackward,
  setSpeed,
  /** 直接设置进度（0-100） */
  setProgress: (pct: number) => {
    const idx = Math.round((pct / 100) * (totalFrames.value - 1))
    seekTo(idx)
  },
  currentFrameIndex,
  isPlaying,
  currentSpeed
})
</script>

<template>
  <div class="aoo-animation">
    <!-- ── 统计面板 ── -->
    <div v-if="showStats" class="aoo-animation__stats">
      <div class="stats-row">
        <!-- 迭代进度 -->
        <div class="stat-item stat-item--iteration">
          <span class="stat-label">迭代</span>
          <span class="stat-value stat-value--large">
            {{ currentIteration }}
            <span class="stat-suffix">/ {{ totalIterations }}</span>
          </span>
        </div>

        <!-- 最优适应度 -->
        <div class="stat-item stat-item--best">
          <span class="stat-label">最优适应度</span>
          <span class="stat-value stat-value--best">
            {{ currentBestFitness.toFixed(4) }}
          </span>
        </div>

        <!-- 平均适应度 -->
        <div class="stat-item stat-item--avg">
          <span class="stat-label">平均适应度</span>
          <span class="stat-value stat-value--avg">
            {{ currentAvgFitness.toFixed(4) }}
          </span>
        </div>

        <!-- 四分位区间 Q1~Q3 -->
        <div v-if="currentQuartile" class="stat-item stat-item--quartile">
          <span class="stat-label">四分位区间</span>
          <span class="stat-value stat-value--quartile">
            {{ currentQuartile.q1.toFixed(3) }} ~ {{ currentQuartile.q3.toFixed(3) }}
          </span>
        </div>

        <!-- 种群多样性 -->
        <div class="stat-item stat-item--diversity">
          <span class="stat-label">种群多样性</span>
          <span class="stat-value stat-value--diversity">
            {{ (currentDiversity * 100).toFixed(1) }}%
          </span>
          <div class="diversity-bar">
            <div class="diversity-bar__fill" :style="{ width: `${currentDiversity * 100}%` }" />
          </div>
        </div>

        <!-- 种群规模 -->
        <div v-if="populationSize > 0" class="stat-item stat-item--pop">
          <span class="stat-label">种群规模</span>
          <span class="stat-value">{{ populationSize }}</span>
        </div>
      </div>
    </div>

    <!-- ── 图表主体 ── -->
    <div ref="chartContainer" class="aoo-animation__chart" :style="{ height: `${height}px` }" />

    <!-- ── 播放控制栏 ── -->
    <div v-if="showControls" class="aoo-animation__controls">
      <div class="controls-left">
        <!-- 重播 -->
        <button class="control-btn" title="从头播放" :disabled="totalFrames <= 1" @click="replay">
          <ReloadOutlined />
        </button>

        <!-- 后退一帧 -->
        <button
          class="control-btn"
          title="后退一帧"
          :disabled="currentFrameIndex <= 0"
          @click="stepBackward"
        >
          <StepBackwardOutlined />
        </button>

        <!-- 播放 / 暂停 -->
        <button
          class="control-btn control-btn--play"
          :title="isPlaying ? '暂停' : '播放'"
          :disabled="totalFrames <= 1"
          @click="togglePlayPause"
        >
          <PauseCircleOutlined v-if="isPlaying" />
          <CaretRightOutlined v-else />
        </button>

        <!-- 前进一帧 -->
        <button
          class="control-btn"
          title="前进一帧"
          :disabled="currentFrameIndex >= totalFrames - 1"
          @click="stepForward"
        >
          <StepForwardOutlined />
        </button>
      </div>

      <!-- 进度条 -->
      <div class="controls-center">
        <span class="progress-label">{{ currentIteration }}</span>
        <div class="progress-track">
          <input
            type="range"
            class="progress-slider"
            :min="0"
            :max="Math.max(totalFrames - 1, 0)"
            :value="currentFrameIndex"
            :disabled="totalFrames <= 1"
            @input="seekTo(Number(($event.target as HTMLInputElement).value))"
          />
          <div class="progress-fill" :style="{ width: `${progress}%` }" />
        </div>
        <span class="progress-label">{{ totalIterations }}</span>
      </div>

      <!-- 速度选择 -->
      <div class="controls-right">
        <span class="speed-label">
          <ThunderboltOutlined />
        </span>
        <div class="speed-group">
          <button
            v-for="opt in SPEED_OPTIONS"
            :key="opt.value"
            class="speed-btn"
            :class="{ 'speed-btn--active': currentSpeed === opt.value }"
            @click="setSpeed(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>
    </div>

    <!-- ── 图例提示 ── -->
    <div v-if="totalFrames > 0" class="aoo-animation__legend-tip">
      <span class="legend-dot legend-dot--elite" />
      <span class="legend-text">最优</span>
      <span class="legend-dot legend-dot--normal" />
      <span class="legend-text">普通</span>
      <span class="legend-dot legend-dot--exploring" />
      <span class="legend-text">探索中</span>
    </div>

    <!-- ── 空状态 ── -->
    <div v-if="totalFrames === 0" class="aoo-animation__empty">
      <p>暂无收敛数据，请先启动 AOO 路径生成</p>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════ 容器 ═══════════ */
.aoo-animation {
  width: 100%;
  background: rgba(10, 13, 20, 0.7);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 12px;
  box-shadow:
    0 12px 48px rgba(0, 0, 0, 0.5),
    0 0 0 1px rgba(74, 108, 247, 0.05);
  overflow: hidden;
  transition: box-shadow 250ms cubic-bezier(0.4, 0, 0.2, 1);
}

.aoo-animation:hover {
  box-shadow:
    0 16px 56px rgba(0, 0, 0, 0.55),
    0 0 0 1px rgba(212, 163, 115, 0.2);
}

/* ═══════════ 统计面板 ═══════════ */
.aoo-animation__stats {
  padding: 16px 24px 0;
}

.stats-row {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-label {
  font-size: 11px;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 500;
}

.stat-value {
  font-size: 14px;
  font-weight: 600;
  color: #f8fafc;
  font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace;
}

.stat-value--large {
  font-size: 22px;
  font-weight: 700;
  color: #faedcd;
}

.stat-suffix {
  font-size: 13px;
  font-weight: 400;
  color: #94a3b8;
}

.stat-value--best {
  color: #ff7a7c;
}

.stat-value--avg {
  color: #8faeff;
}

.stat-value--quartile {
  color: #b8a99a;
  font-size: 13px;
  letter-spacing: -0.2px;
}

.stat-value--diversity {
  color: #ffb84d;
}

/* 多样性迷你进度条 */
.diversity-bar {
  width: 60px;
  height: 3px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
  margin-top: 4px;
  overflow: hidden;
}

.diversity-bar__fill {
  height: 100%;
  background: linear-gradient(90deg, #fa8c16, #ffb84d);
  border-radius: 2px;
  transition: width 400ms cubic-bezier(0.4, 0, 0.2, 1);
}

/* ═══════════ 图表区域 ═══════════ */
.aoo-animation__chart {
  width: 100%;
  min-height: clamp(220px, 18.75rem + 2vw, 340px);
}

/* ═══════════ 播放控制栏 ═══════════ */
.aoo-animation__controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 24px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.controls-left,
.controls-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

/* 控制按钮 */
.control-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  color: #cbd5e1;
  cursor: pointer;
  font-size: 14px;
  transition:
    background 150ms ease,
    border-color 150ms ease,
    color 150ms ease,
    transform 100ms ease;
}

.control-btn:hover:not(:disabled) {
  background: rgba(74, 108, 247, 0.16);
  border-color: rgba(74, 108, 247, 0.5);
  color: #8faeff;
}

.control-btn:active:not(:disabled) {
  transform: scale(0.95);
}

.control-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.control-btn--play {
  width: 38px;
  height: 38px;
  font-size: 18px;
  border-color: rgba(212, 163, 115, 0.5);
  color: #d4a373;
  background: rgba(212, 163, 115, 0.1);
}

.control-btn--play:hover:not(:disabled) {
  background: rgba(212, 163, 115, 0.18);
}

/* 进度条 */
.controls-center {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 120px;
}

.progress-label {
  font-size: 11px;
  color: #94a3b8;
  font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace;
  min-width: 28px;
  text-align: center;
  user-select: none;
}

.progress-track {
  flex: 1;
  position: relative;
  height: 4px;
}

.progress-slider {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
  margin: 0;
  z-index: 2;
}

.progress-slider:disabled {
  cursor: not-allowed;
}

.progress-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: linear-gradient(90deg, #4a6cf7, #00d4ff);
  border-radius: 2px;
  pointer-events: none;
  z-index: 1;
  transition: width 200ms linear;
}

.progress-track::before {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.12);
  border-radius: 2px;
}

/* 速度选择 */
.speed-label {
  color: #94a3b8;
  font-size: 14px;
  display: flex;
  align-items: center;
}

.speed-group {
  display: flex;
  gap: 2px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  padding: 2px;
}

.speed-btn {
  padding: 3px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #94a3b8;
  font-size: 12px;
  font-weight: 500;
  font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace;
  cursor: pointer;
  transition:
    background 150ms ease,
    color 150ms ease;
}

.speed-btn:hover {
  color: #f8fafc;
  background: rgba(255, 255, 255, 0.08);
}

.speed-btn--active {
  background: rgba(74, 108, 247, 0.2);
  color: #8faeff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

/* ═══════════ 图例提示 ─══════════ */
.aoo-animation__legend-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px 10px;
  padding: 0 24px 14px;
  flex-wrap: wrap;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.legend-dot--elite {
  background: #ff4d4f;
}

.legend-dot--normal {
  background: #4f7cff;
}

.legend-dot--exploring {
  background: #52c41a;
}

.legend-text {
  font-size: 11px;
  color: #94a3b8;
}

/* ═══════════ 空状态 ═══════════ */
.aoo-animation__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: #94a3b8;
  font-size: 14px;
}

/* ═══════════ 响应式 ═══════════ */
@media (max-width: 768px) {
  .aoo-animation__stats {
    padding: 12px 16px 0;
  }

  .stats-row {
    gap: 12px;
  }

  .stat-value--large {
    font-size: 18px;
  }

  .aoo-animation__controls {
    flex-direction: column;
    gap: 10px;
    padding: 10px 16px 14px;
  }

  .controls-center {
    width: 100%;
  }

  .aoo-animation__legend-tip {
    padding: 0 16px 12px;
  }
}

@media (max-width: 480px) {
  .stats-row {
    gap: 8px;
  }

  .stat-label {
    font-size: 10px;
  }

  .stat-value {
    font-size: 12px;
  }

  .stat-value--large {
    font-size: 16px;
  }

  .controls-right {
    display: none; /* 小屏幕隐藏速度选择 */
  }
}
</style>
