<script setup lang="ts">
/**
 * LearningPathView.vue — AOO 学习路径展示组件
 *
 * 两种视图模式：
 *   1. 甘特图 (Gantt)：ECharts custom series 渲染，X=天数 / Y=任务，按类型着色
 *   2. 时间轴 (Timeline)：垂直时间线，按天分组，任务卡片展示
 *
 * 支持三条差异化路径切换（效率型 / 均衡型 / 稳健型），联动更新
 * 统计数据面板：总天数、总时长、覆盖知识点、日均时长、认知负荷指数
 */
import { ref, computed, watch, onMounted, onUnmounted, nextTick, type Component } from 'vue'
import * as echarts from 'echarts'
import { usePathStore } from '@/stores/path'
import type { AlternativePath, DailyTaskView, LearningTask } from '@/types'
import {
  BarChartOutlined,
  FieldTimeOutlined,
  ClockCircleOutlined,
  BookOutlined,
  BulbOutlined,
  ThunderboltOutlined,
  DashboardOutlined,
  VideoCameraOutlined,
  CheckCircleOutlined,
  ReadOutlined,
  FileTextOutlined,
  ProjectOutlined,
  EditOutlined,
  RocketOutlined,
  SlidersOutlined,
  SafetyOutlined,
  CloseOutlined
} from '@ant-design/icons-vue'

// ============ Props ============
const props = withDefaults(
  defineProps<{
    /** 组件高度（px） */
    height?: number | string
    /** 初始视图模式 */
    initialView?: 'gantt' | 'timeline'
    /** 是否显示统计面板 */
    showStats?: boolean
    /** 是否显示路径变体选择器 */
    showVariants?: boolean
    /** 是否展示图例 */
    showLegend?: boolean
  }>(),
  {
    height: 'auto',
    initialView: 'gantt',
    showStats: true,
    showVariants: true,
    showLegend: true
  }
)

// ============ Emits ============
const emit = defineEmits<{
  (e: 'task-click', task: LearningTask): void
  (e: 'variant-change', pathId: string, index: number): void
}>()

// ============ Store ============
const pathStore = usePathStore()

// ============ Reactive State ============
const viewMode = ref<'gantt' | 'timeline'>(props.initialView)
const selectedVariantIndex = ref(0) // 0 = 当前路径, 1+ = 备选索引
const ganttRef = ref<HTMLDivElement | null>(null)
let chartInstance: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

/** 是否窄屏（移动端）。用于甘特图自动降级为时间轴 + Tooltip 转 Bottom Sheet */
const isMobile = ref(false)
/** 用户是否手动切换过视图 —— 手动切换后不再自动覆盖用户选择 */
const userPickedView = ref(false)
let mobileMql: MediaQueryList | null = null

/** 悬停中的任务（Timeline Tooltip / 移动端 Bottom Sheet） */
const hoveredTask = ref<LearningTask | null>(null)

/** 手动切换视图（工具栏按钮） */
function switchView(mode: 'gantt' | 'timeline') {
  userPickedView.value = true
  viewMode.value = mode
}

/** 根据窄屏状态自动切换视图 */
function applyResponsiveView(matches: boolean) {
  isMobile.value = matches
  hoveredTask.value = null
  if (userPickedView.value) return
  // 窄屏下甘特图横轴天数过多难以阅读，自动降级为时间轴
  viewMode.value = matches ? 'timeline' : props.initialView
}

function onMobileChange(e: MediaQueryListEvent) {
  applyResponsiveView(e.matches)
}
function showTaskTooltip(task: LearningTask) {
  // 移动端不响应 hover，改由点击触发 Bottom Sheet
  if (isMobile.value) return
  hoveredTask.value = task
}
function hideTaskTooltip() {
  if (isMobile.value) return
  hoveredTask.value = null
}
/** 移动端：点击任务卡片弹出 Bottom Sheet */
function toggleTaskSheet(task: LearningTask) {
  if (!isMobile.value) return
  hoveredTask.value = hoveredTask.value?.id === task.id ? null : task
}
function closeTaskSheet() {
  hoveredTask.value = null
}

// ============ 任务类型配色 ============
interface TaskTypeStyle {
  color: string
  bg: string
  label: string
  icon: Component
}
const TASK_TYPE_CONFIG: {
  [K in 'video' | 'quiz' | 'reading' | 'article' | 'project' | 'exercise']: TaskTypeStyle
} = {
  video: { color: '#1890FF', bg: 'rgba(24,144,255,0.12)', label: '视频', icon: VideoCameraOutlined },
  quiz: { color: '#FA8C16', bg: 'rgba(250,140,22,0.12)', label: '测验', icon: CheckCircleOutlined },
  reading: { color: '#52C41A', bg: 'rgba(82,196,26,0.12)', label: '阅读', icon: ReadOutlined },
  article: { color: '#52C41A', bg: 'rgba(82,196,26,0.12)', label: '阅读', icon: FileTextOutlined },
  project: { color: '#722ED1', bg: 'rgba(114,46,209,0.12)', label: '项目', icon: ProjectOutlined },
  exercise: { color: '#13C2C2', bg: 'rgba(19,194,194,0.12)', label: '练习', icon: EditOutlined }
}

/** 任务类型图例列表 */
const taskTypeLegends = [
  { key: 'video', ...TASK_TYPE_CONFIG.video },
  { key: 'quiz', ...TASK_TYPE_CONFIG.quiz },
  { key: 'reading', ...TASK_TYPE_CONFIG.reading },
  { key: 'project', ...TASK_TYPE_CONFIG.project },
  { key: 'exercise', ...TASK_TYPE_CONFIG.exercise }
]

// ============ 路径变体配色 ============
const VARIANT_THEMES = [
  {
    icon: RocketOutlined,
    label: '速成冲刺型',
    description: '高学习效果，高负荷推进，适合有基础的学习者',
    color: '#FF6B35',
    bg: 'rgba(255,107,53,0.08)',
    border: 'rgba(255,107,53,0.3)',
    intensityLabel: '高强度'
  },
  {
    icon: SlidersOutlined,
    label: '稳扎稳打型',
    description: '平衡学习效果与认知负荷，循序渐进',
    color: '#4F7CFF',
    bg: 'rgba(79,124,255,0.08)',
    border: 'rgba(79,124,255,0.3)',
    intensityLabel: '适中'
  },
  {
    icon: SafetyOutlined,
    label: '查漏补缺型',
    description: '低负荷，重点攻克薄弱知识点',
    color: '#52C41A',
    bg: 'rgba(82,196,26,0.08)',
    border: 'rgba(82,196,26,0.3)',
    intensityLabel: '低强度'
  }
]

// ============ 数据源 ============
const dailyTaskViews = computed<DailyTaskView[]>(() => pathStore.dailyTaskViews)
const alternativePaths = computed<AlternativePath[]>(() => pathStore.alternativePaths)
const isGenerating = computed(() => pathStore.isGenerating)

/** 当前展示路径的总天数 */
const totalDays = computed(() => pathStore.totalDays)

/** 当前展示路径的任务总数 */
const totalTasks = computed(() => pathStore.taskCount)

/** 当前展示路径的总时长（小时） */
const totalEstimatedHours = computed(() => pathStore.estimatedHours)

// ============ 扁平任务列表（甘特图核心数据） ============
interface FlatTaskItem {
  id: string
  name: string
  day: number
  orderIndex: number
  knowledgePoint: string
  estimatedMinutes: number
  difficulty: number
  taskType: string
  completed: boolean
}

const flatTasks = computed<FlatTaskItem[]>(() => {
  return dailyTaskViews.value.flatMap((dayView) =>
    dayView.tasks.map((task) => ({
      id: task.id,
      name: task.title,
      day: dayView.dayIndex,
      orderIndex: task.orderIndex,
      knowledgePoint: task.knowledgePoint,
      estimatedMinutes: task.estimatedMinutes,
      difficulty: task.difficulty,
      taskType: task.resources?.[0]?.type || 'reading',
      completed: false
    }))
  )
})

/** 路径变体列表（当前路径 + 备选路径） */
const variants = computed(() => {
  const list = [
    {
      id: pathStore.pathId || 'current',
      index: 0,
      label: VARIANT_THEMES[1]!.label, // 默认当前是均衡型
      icon: VARIANT_THEMES[1]!.icon,
      description: VARIANT_THEMES[1]!.description,
      color: VARIANT_THEMES[1]!.color,
      bg: VARIANT_THEMES[1]!.bg,
      border: VARIANT_THEMES[1]!.border,
      intensityLabel: VARIANT_THEMES[1]!.intensityLabel,
      totalDays: totalDays.value,
      totalTasks: totalTasks.value,
      totalEstimatedHours: totalEstimatedHours.value,
      highlights: [] as string[],
      isCurrent: true
    }
  ]

  alternativePaths.value.forEach((alt, i) => {
    const theme = (i === 0 ? VARIANT_THEMES[0] : VARIANT_THEMES[2])!
    list.push({
      id: alt.id,
      index: i + 1,
      label: theme.label,
      icon: theme.icon,
      description: theme.description,
      color: theme.color,
      bg: theme.bg,
      border: theme.border,
      intensityLabel: theme.intensityLabel,
      totalDays: alt.totalDays,
      totalTasks: alt.totalTasks,
      totalEstimatedHours: alt.totalEstimatedHours,
      highlights: alt.highlights || [],
      isCurrent: false
    })
  })

  return list.length > 1 ? list : []
})

// ============ 统计数据 ============
const uniqueKnowledgePoints = computed(() => {
  const kps = new Set<string>()
  flatTasks.value.forEach((t) => {
    if (t.knowledgePoint) kps.add(t.knowledgePoint)
  })
  return kps.size
})

const avgDailyMinutes = computed(() => {
  if (totalDays.value <= 0) return 0
  return Math.round((totalEstimatedHours.value * 60) / totalDays.value)
})

const cognitiveLoadIndex = computed(() => {
  if (flatTasks.value.length === 0) return 0
  const avgDiff = flatTasks.value.reduce((s, t) => s + t.difficulty, 0) / flatTasks.value.length
  const intensityFactor = avgDailyMinutes.value > 120 ? 1.3 : avgDailyMinutes.value > 60 ? 1 : 0.8
  return Math.min(100, Math.round(avgDiff * 20 * intensityFactor))
})

const dailyDensity = computed(() => {
  if (totalDays.value <= 0) return 0
  return Number((totalTasks.value / totalDays.value).toFixed(1))
})

interface StatItem {
  key: string
  label: string
  value: string | number
  unit?: string
  icon: Component | string
  color: string
}

const stats = computed<StatItem[]>(() => [
  {
    key: 'days',
    label: '总学习天数',
    value: totalDays.value,
    unit: '天',
    icon: ClockCircleOutlined,
    color: '#4F7CFF'
  },
  {
    key: 'hours',
    label: '总学习时长',
    value: totalEstimatedHours.value.toFixed(1),
    unit: '小时',
    icon: ThunderboltOutlined,
    color: '#FA8C16'
  },
  {
    key: 'kps',
    label: '覆盖知识点',
    value: uniqueKnowledgePoints.value,
    unit: '个',
    icon: BulbOutlined,
    color: '#52C41A'
  },
  {
    key: 'avg-daily',
    label: '日均学习',
    value: `${Math.floor(avgDailyMinutes.value / 60)}h${avgDailyMinutes.value % 60}m`,
    icon: FieldTimeOutlined,
    color: '#13C2C2'
  },
  {
    key: 'load',
    label: '认知负荷指数',
    value: cognitiveLoadIndex.value,
    unit: '/100',
    icon: DashboardOutlined,
    color:
      cognitiveLoadIndex.value > 70
        ? '#FF4D4F'
        : cognitiveLoadIndex.value > 40
          ? '#FA8C16'
          : '#52C41A'
  }
])

// ============ 辅助函数 ============
function getTaskConfig(taskType: string): TaskTypeStyle {
  return TASK_TYPE_CONFIG[taskType as keyof typeof TASK_TYPE_CONFIG] || TASK_TYPE_CONFIG.reading
}

function getDifficultyStars(difficulty: number): string {
  return '★'.repeat(difficulty) + '☆'.repeat(5 - difficulty)
}

function getDifficultyColor(difficulty: number): string {
  const colors = ['#52C41A', '#73D13D', '#FA8C16', '#FF7A45', '#FF4D4F']
  return colors[difficulty - 1] ?? colors[2] ?? '#52C41A'
}

/** 按可用像素宽度截断文字（中文约 11px/字，西文约 6px/字），超出加省略号 */
function fitText(name: string, maxPx: number): string {
  if (maxPx <= 0) return ''
  let used = 0
  let result = ''
  for (const ch of name) {
    const w = /[一-龥]/.test(ch) ? 11 : 6
    if (used + w > maxPx) {
      return result + '…'
    }
    used += w
    result += ch
  }
  return result
}

// ============ 甘特图渲染 ============
function initChart(): void {
  if (!ganttRef.value) return
  if (chartInstance) {
    chartInstance.dispose()
  }
  chartInstance = echarts.init(ganttRef.value, undefined, { devicePixelRatio: 2 })
  renderGanttChart()
}

function renderGanttChart(): void {
  if (!chartInstance) return
  const tasks = flatTasks.value
  if (tasks.length === 0) {
    chartInstance.clear()
    return
  }

  const maxDay = tasks.length > 0 ? Math.max(...tasks.map((t) => t.day)) : 1
  const taskNames = tasks.map((t) => `第${t.day}天 · ${t.name}`)
  const rowHeight = 40
  // 超过 12 条时启用 dataZoom，画布高度按「可视 12 行」固定，
  // 保证每行高度稳定在 rowHeight，滚动时不会被压扁
  const visibleRows = Math.min(tasks.length, 12)
  const chartHeight = Math.max(300, visibleRows * rowHeight + 80)

  // 动态调整容器高度
  if (ganttRef.value) {
    ganttRef.value.style.height = `${chartHeight}px`
    chartInstance.resize()
  }

  const option: echarts.EChartsOption = {
    tooltip: {
      backgroundColor: 'rgba(10,13,20,0.95)',
      borderColor: 'rgba(212,163,115,0.20)',
      borderWidth: 1,
      borderRadius: 8,
      padding: [12, 16],
      textStyle: { color: '#F8FAFC', fontSize: 13 },
      formatter: (params: any) => {
        if (params.dataIndex == null) return ''
        const t = tasks[params.dataIndex]
        if (!t) return ''
        const config = getTaskConfig(t.taskType)
        return `
          <div style="font-weight:600;font-size:14px;margin-bottom:8px;">
            ${t.name}
          </div>
          <div style="display:flex;flex-direction:column;gap:4px;color:#94A3B8;">
            <span>知识点：${t.knowledgePoint || '—'}</span>
            <span>类型：${config.label}</span>
            <span>时长：${t.estimatedMinutes} 分钟</span>
            <span>难度：${getDifficultyStars(t.difficulty)}</span>
            <span>第 ${t.day} 天 · 第 ${t.orderIndex} 个任务</span>
          </div>
        `
      }
    },
    grid: {
      left: 24,
      right: 48,
      top: 16,
      bottom: 48,
      containLabel: true
    },
    xAxis: {
      type: 'value' as const,
      name: '学习天数',
      nameLocation: 'middle' as const,
      nameGap: 32,
      nameTextStyle: { color: '#CBD5E1', fontSize: 12, fontWeight: 500 },
      min: 0.5,
      max: maxDay + 0.5,
      interval: 1,
      axisLabel: {
        formatter: (v: number) => {
          if (v === Math.round(v)) return `第${v}天`
          return ''
        },
        color: '#94A3B8',
        fontSize: 12
      },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
      axisTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: { type: 'dashed' as const, color: 'rgba(255,255,255,0.06)' }
      }
    },
    yAxis: {
      type: 'category' as const,
      data: taskNames,
      inverse: true,
      axisLabel: {
        width: 180,
        overflow: 'truncate' as const,
        fontSize: 12,
        color: '#94A3B8'
      },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false }
    },
    dataZoom:
      tasks.length > 12
        ? [
            {
              type: 'slider' as const,
              yAxisIndex: 0,
              // 关键：只平移可视窗口，不过滤数据。
              // 若使用默认的 'filter'，窗口外的数据点会被剔除，
              // 自定义 series 将拿不到任务而导致条目整片消失。
              filterMode: 'none' as const,
              start: 0,
              end: Math.min(100, Math.round((12 * 100) / tasks.length)),
              width: 18,
              handleSize: 0,
              backgroundColor: 'transparent',
              borderColor: 'transparent',
              fillerColor: 'rgba(79,124,255,0.15)',
              left: 0,
              zoomLock: true,
              brushSelect: false
            },
            {
              type: 'inside' as const,
              yAxisIndex: 0,
              filterMode: 'none' as const,
              start: 0,
              end: Math.min(100, Math.round((12 * 100) / tasks.length)),
              zoomOnMouseWheel: false,
              moveOnMouseWheel: true,
              moveOnMouseMove: false
            }
          ]
        : [],
    series: [
      {
        type: 'custom',
        renderItem: (_params: any, api: any) => {
          // 行号来自数据本身（api.value(1)），而非 dataIndex，
          // 这样 dataZoom 平移时坐标依然能正确映射到当前可视行
          const rowIdx = Number(api.value(1))
          if (!Number.isFinite(rowIdx)) return null
          const task = tasks[rowIdx]
          if (!task) return null
          const day = Number(api.value(0))
          const config = getTaskConfig(task.taskType)

          const [xStart, y] = api.coord([day - 0.46, rowIdx])
          const [xEnd] = api.coord([day + 0.46, rowIdx])

          // 超出绘图区（被 dataZoom 移出视野）的行直接不绘制，
          // 避免图元溢出到坐标轴与提示条上
          const grid = api.coordSys as { y: number; height: number } | undefined
          if (grid && (y < grid.y - 20 || y > grid.y + grid.height + 20)) {
            return null
          }

          const rectWidth = Math.max(xEnd - xStart - 4, 14)
          const rectHeight = 32
          const rectX = xStart + 2
          const rectY = y - rectHeight / 2
          const innerPad = 10

          // 按像素宽度截断文字，避免超出绿色框
          const avail = rectWidth - innerPad - 6
          const text = fitText(task.name, avail)

          const children: any[] = [
            // 主矩形 — 极轻底色块
            {
              type: 'rect',
              shape: {
                x: rectX,
                y: rectY,
                width: rectWidth,
                height: rectHeight,
                r: [5, 5, 5, 5]
              },
              style: {
                fill: config.color + '22',
                stroke: config.color + '55',
                lineWidth: 1
              },
              z2: 2
            },
            // 左侧指示条
            {
              type: 'rect',
              shape: {
                x: rectX,
                y: rectY + 6,
                width: 3,
                height: rectHeight - 12,
                r: [2, 0, 0, 2]
              },
              style: {
                fill: config.color + 'AA'
              },
              z2: 3
            }
          ]

          // 文字标签 — 仅在框内放得下时显示，并用 clip 裁剪兜底
          if (text && avail > 12) {
            children.push({
              type: 'text',
              style: {
                text,
                x: rectX + innerPad,
                y,
                fill: '#E2E8F0',
                font: '500 11px Inter, PingFang SC, sans-serif',
                textVerticalAlign: 'middle' as const,
                textAlign: 'left' as const
              },
              clipRect: {
                x: rectX + innerPad - 1,
                y: rectY,
                width: Math.max(rectWidth - innerPad - 4, 0),
                height: rectHeight
              },
              z2: 4
            })
          }

          return { type: 'group', children }
        },
        // value[1] 必须是该任务所在的真实行索引，
        // 供 renderItem 定位与 yAxis 类目对齐
        data: tasks.map((t, i) => ({
          value: [t.day, i],
          name: t.name
        })),
        encode: { x: 0, y: 1 },
        clip: true,
        emphasis: {
          scale: false
        }
      } as any
    ]
  }

  chartInstance.setOption(option, true)
}

// ============ 路径切换 ============
async function switchVariant(variantIndex: number) {
  if (variantIndex === selectedVariantIndex.value) return
  const variant = variants.value[variantIndex]
  if (!variant) return

  if (variant.isCurrent) {
    selectedVariantIndex.value = 0
    emit('variant-change', variant.id, 0)
    await nextTick()
    renderGanttChart()
    return
  }

  try {
    selectedVariantIndex.value = variantIndex
    await pathStore.selectAlternativePath(variant.id)
    emit('variant-change', variant.id, variantIndex)
    await nextTick()
    renderGanttChart()
  } catch {
    selectedVariantIndex.value = 0
  }
}

// ============ 生命周期 ============
onMounted(async () => {
  // 先判定窄屏，避免移动端先渲染甘特图再切换造成闪烁
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    mobileMql = window.matchMedia('(max-width: 768px)')
    applyResponsiveView(mobileMql.matches)
    if (typeof mobileMql.addEventListener === 'function') {
      mobileMql.addEventListener('change', onMobileChange)
    } else {
      // Safari < 14 回退
      mobileMql.addListener(onMobileChange)
    }
  }

  await nextTick()
  if (viewMode.value === 'gantt') {
    initChart()
  }

  if (ganttRef.value) {
    resizeObserver = new ResizeObserver(() => {
      chartInstance?.resize()
    })
    resizeObserver.observe(ganttRef.value)
  }

  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  chartInstance?.dispose()
  chartInstance = null
  resizeObserver?.disconnect()
  resizeObserver = null
  window.removeEventListener('resize', handleResize)

  if (mobileMql) {
    if (typeof mobileMql.removeEventListener === 'function') {
      mobileMql.removeEventListener('change', onMobileChange)
    } else {
      mobileMql.removeListener(onMobileChange)
    }
    mobileMql = null
  }
})

function handleResize() {
  chartInstance?.resize()
}

// ============ Watchers ============
watch(
  () => flatTasks.value.length,
  async () => {
    await nextTick()
    if (viewMode.value === 'gantt') {
      if (!chartInstance && ganttRef.value) {
        initChart()
      } else {
        renderGanttChart()
      }
    }
  }
)

watch(viewMode, async (mode) => {
  if (mode === 'gantt') {
    await nextTick()
    initChart()
  }
})

// 监听备选路径更新，重置选中索引
watch(
  () => alternativePaths.value.length,
  (newLen) => {
    if (newLen === 0) {
      selectedVariantIndex.value = 0
    }
  }
)
</script>

<template>
  <div
    class="learning-path-view"
    :style="{ height: typeof height === 'number' ? height + 'px' : height }"
  >
    <!-- ═══ 统计面板 ═══ -->
    <div v-if="showStats && stats.length > 0" class="stats-row">
      <div v-for="stat in stats" :key="stat.key" class="stat-card">
        <div class="stat-icon-wrap" :style="{ background: stat.color + '18', color: stat.color }">
          <component :is="stat.icon" />
        </div>
        <div class="stat-content">
          <span class="stat-value"
            >{{ stat.value }}<small v-if="stat.unit">{{ stat.unit }}</small></span
          >
          <span class="stat-label">{{ stat.label }}</span>
        </div>
      </div>
    </div>

    <!-- ═══ 主卡片 ═══ -->
    <div class="main-card">
      <!-- ── 路径变体选择器 ── -->
      <div v-if="showVariants && variants.length > 1" class="variant-section">
        <div class="variant-label">
          <BulbOutlined />
          <span>选择适合你的学习方案</span>
        </div>
        <div class="variant-row">
          <div
            v-for="(variant, vi) in variants"
            :key="variant.id"
            class="variant-card"
            :class="{ active: selectedVariantIndex === vi }"
            :style="{
              '--variant-color': variant.color,
              '--variant-bg': variant.bg,
              '--variant-border': variant.border
            }"
            @click="switchVariant(vi)"
          >
            <div class="variant-top">
              <component :is="variant.icon" class="variant-icon" />
              <span class="variant-name">{{ variant.label }}</span>
              <a-tag :color="variant.color" size="small" class="variant-intensity">
                {{ variant.intensityLabel }}
              </a-tag>
            </div>
            <p class="variant-desc">{{ variant.description }}</p>
            <div class="variant-stats">
              <span class="vs-item">
                <ClockCircleOutlined />
                {{ variant.totalDays }}天
              </span>
              <span class="vs-item">
                <BookOutlined />
                {{ variant.totalTasks }}个任务
              </span>
              <span class="vs-item">
                <FieldTimeOutlined />
                {{ variant.totalEstimatedHours.toFixed(1) }}h
              </span>
            </div>
            <div v-if="variant.highlights.length > 0" class="variant-highlights">
              <span v-for="h in variant.highlights" :key="h" class="highlight-tag">{{ h }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ── 视图切换 + 图例 ── -->
      <div class="toolbar-row">
        <div class="view-tabs">
          <button
            class="view-tab"
            :class="{ active: viewMode === 'gantt' }"
            :title="isMobile ? '窄屏下甘特图可读性较差，建议使用时间轴' : '甘特图'"
            @click="switchView('gantt')"
          >
            <BarChartOutlined />
            <span>甘特图</span>
          </button>
          <button
            class="view-tab"
            :class="{ active: viewMode === 'timeline' }"
            @click="switchView('timeline')"
          >
            <FieldTimeOutlined />
            <span>时间轴</span>
          </button>
        </div>

        <div v-if="showLegend" class="legend-row">
          <span
            v-for="type in taskTypeLegends"
            :key="type.key"
            class="legend-dot"
            :style="{ background: type.color }"
            :title="type.label"
          />
          <span class="legend-divider">|</span>
          <span class="legend-label">{{ flatTasks.length }} 个任务</span>
          <span class="legend-divider">·</span>
          <span class="legend-label">{{ totalDays }} 天</span>
        </div>
      </div>

      <!-- ── 甘特图视图 ── -->
      <div v-show="viewMode === 'gantt'" class="gantt-wrap">
        <!-- 加载中 -->
        <div v-if="isGenerating" class="chart-placeholder">
          <a-spin size="large" tip="正在生成学习路径..." />
        </div>
        <!-- 无数据 -->
        <div v-else-if="flatTasks.length === 0" class="chart-placeholder">
          <div class="empty-icon">
            <BarChartOutlined />
          </div>
          <p class="empty-text">暂无学习路径数据</p>
          <p class="empty-hint">完成学情测绘后，系统将自动生成个性化学习路径</p>
        </div>
        <!-- 图表 -->
        <div ref="ganttRef" class="gantt-chart" />
      </div>

      <!-- ── 时间轴视图 ── -->
      <div v-show="viewMode === 'timeline'" class="timeline-wrap">
        <!-- 加载中 -->
        <div v-if="isGenerating" class="chart-placeholder">
          <a-spin size="large" tip="正在生成学习路径..." />
        </div>
        <!-- 无数据 -->
        <div v-else-if="dailyTaskViews.length === 0" class="chart-placeholder">
          <div class="empty-icon">
            <FieldTimeOutlined />
          </div>
          <p class="empty-text">暂无学习路径数据</p>
          <p class="empty-hint">完成学情测绘后，系统将自动生成个性化学习路径</p>
        </div>
        <!-- 时间轴 -->
        <div v-else class="timeline-list">
          <div class="timeline-line-track" />
          <div v-for="dayView in dailyTaskViews" :key="dayView.dayIndex" class="timeline-day-group">
            <!-- 天数标记 -->
            <div class="timeline-marker">
              <div
                class="marker-dot"
                :style="{ background: getDifficultyColor(dayView.difficulty) }"
              />
              <div class="marker-content">
                <div class="marker-header">
                  <span class="day-number">{{ dayView.dayLabel }}</span>
                  <span class="day-date">{{ dayView.date }}</span>
                  <a-tag
                    :color="
                      dayView.difficulty > 3.5
                        ? 'red'
                        : dayView.difficulty > 2.5
                          ? 'orange'
                          : 'green'
                    "
                    size="small"
                  >
                    难度 {{ dayView.difficulty }}/5
                  </a-tag>
                </div>
              </div>
            </div>

            <!-- 任务卡片列表 -->
            <div class="timeline-tasks">
              <div
                v-for="task in dayView.tasks"
                :key="task.id"
                class="task-card"
                :class="{ 'is-tooltip-open': hoveredTask?.id === task.id }"
                @click="isMobile ? toggleTaskSheet(task) : emit('task-click', task)"
                @mouseenter="showTaskTooltip(task)"
                @mouseleave="hideTaskTooltip"
              >
                <div
                  class="task-type-strip"
                  :style="{
                    background: getTaskConfig(task.resources?.[0]?.type || 'reading').color + '99'
                  }"
                />
                <div class="task-body">
                  <div class="task-header-row">
                    <a-tag
                      :color="getTaskConfig(task.resources?.[0]?.type || 'reading').color"
                      size="small"
                    >
                      <component :is="getTaskConfig(task.resources?.[0]?.type || 'reading').icon" />
                      {{ getTaskConfig(task.resources?.[0]?.type || 'reading').label }}
                    </a-tag>
                    <span class="task-duration">{{ task.estimatedMinutes }}分钟</span>
                  </div>
                  <h4 class="task-title">{{ task.title }}</h4>
                </div>

                <!-- Hover Tooltip（桌面端浮层；移动端改用下方 Bottom Sheet） -->
                <Transition name="tooltip-fade">
                  <div v-if="!isMobile && hoveredTask?.id === task.id" class="task-tooltip">
                    <div class="tt-row">
                      <span class="tt-label">知识点</span>
                      <span class="tt-value tt-kp">{{ task.knowledgePoint }}</span>
                    </div>
                    <div class="tt-row">
                      <span class="tt-label">难度</span>
                      <span
                        class="tt-value"
                        :style="{ color: getDifficultyColor(task.difficulty) }"
                      >
                        {{ getDifficultyStars(task.difficulty) }}
                      </span>
                    </div>
                    <div class="tt-row">
                      <span class="tt-label">预计时间</span>
                      <span class="tt-value">{{ task.estimatedMinutes }} 分钟</span>
                    </div>
                    <p v-if="task.description" class="tt-desc">{{ task.description }}</p>
                    <div v-if="task.resources?.length" class="tt-resources">
                      <span class="tt-resource-label">学习资源</span>
                      <span v-for="res in task.resources" :key="res.title" class="tt-resource-item">
                        {{ res.title }}
                      </span>
                    </div>
                  </div>
                </Transition>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ── 底部汇总 ── -->
      <div v-if="flatTasks.length > 0" class="summary-bar">
        <div class="summary-item">
          <span class="summary-label">知识点覆盖</span>
          <span class="summary-value">{{ uniqueKnowledgePoints }} 个</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">每日任务密度</span>
          <span class="summary-value">{{ dailyDensity }} 个</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">日均学习时长</span>
          <span class="summary-value"
            >{{ Math.floor(avgDailyMinutes / 60) }}h{{ avgDailyMinutes % 60 }}m</span
          >
        </div>
        <div class="summary-item">
          <span class="summary-label">认知负荷评估</span>
          <span
            class="summary-value load-value"
            :class="{
              'load-low': cognitiveLoadIndex < 35,
              'load-mid': cognitiveLoadIndex >= 35 && cognitiveLoadIndex < 70,
              'load-high': cognitiveLoadIndex >= 70
            }"
          >
            {{ cognitiveLoadIndex < 35 ? '轻松' : cognitiveLoadIndex < 70 ? '适中' : '较高' }}
          </span>
        </div>
      </div>
    </div>

    <!-- ── 移动端 Bottom Sheet（替代悬浮 Tooltip，避免超出屏幕） ── -->
    <Teleport to="body">
      <Transition name="sheet-fade">
        <div v-if="isMobile && hoveredTask" class="task-sheet-mask" @click="closeTaskSheet" />
      </Transition>
      <Transition name="sheet-slide">
        <div
          v-if="isMobile && hoveredTask"
          class="task-sheet"
          role="dialog"
          aria-label="任务详情"
          @click.stop
        >
          <div class="sheet-handle" />
          <div class="sheet-header">
            <h4 class="sheet-title">{{ hoveredTask.title }}</h4>
            <button class="sheet-close" aria-label="关闭" @click="closeTaskSheet">
              <CloseOutlined />
            </button>
          </div>
          <div class="sheet-body">
            <div class="tt-row">
              <span class="tt-label">知识点</span>
              <span class="tt-value tt-kp">{{ hoveredTask.knowledgePoint }}</span>
            </div>
            <div class="tt-row">
              <span class="tt-label">难度</span>
              <span class="tt-value" :style="{ color: getDifficultyColor(hoveredTask.difficulty) }">
                {{ getDifficultyStars(hoveredTask.difficulty) }}
              </span>
            </div>
            <div class="tt-row">
              <span class="tt-label">预计时间</span>
              <span class="tt-value">{{ hoveredTask.estimatedMinutes }} 分钟</span>
            </div>
            <p v-if="hoveredTask.description" class="tt-desc">{{ hoveredTask.description }}</p>
            <div v-if="hoveredTask.resources?.length" class="tt-resources">
              <span class="tt-resource-label">学习资源</span>
              <span v-for="res in hoveredTask.resources" :key="res.title" class="tt-resource-item">
                {{ res.title }}
              </span>
            </div>
          </div>
          <button
            class="sheet-action"
            @click="
              () => {
                if (hoveredTask) emit('task-click', hoveredTask)
                closeTaskSheet()
              }
            "
          >
            查看任务详情
          </button>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

/*============================================================ */
/*根容器 */
/*============================================================ */
.learning-path-view {
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
}

/*============================================================ */
/*统计面板 */
/*============================================================ */
.stats-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: @spacing-md;

  @media (max-width: 1024px) {
    grid-template-columns: repeat(3, 1fr);
  }
  @media (max-width: 640px) {
    grid-template-columns: repeat(2, 1fr);
  }
}

.stat-card {
  display: flex;
  align-items: center;
  gap: @spacing-md;
  padding: @spacing-md @spacing-lg;
  .metal-card();
  .metal-card-hover();
}

.stat-icon-wrap {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: @radius-btn;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.stat-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.stat-value {
  font-size: 20px;
  font-weight: @font-weight-heavy;
  color: @brand-oat-300;
  line-height: 1.3;
  font-family: @font-family-mono;

  small {
    font-size: 12px;
    font-weight: @font-weight-medium;
    color: @gray-400;
    margin-left: 2px;
  }
}

.stat-label {
  font-size: @font-size-xs;
  color: @gray-400;
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

/*============================================================ */
/*主卡片 */
/*============================================================ */
.main-card {
  .metal-card();
  overflow: hidden;
}

/*============================================================ */
/*路径变体选择器 */
/*============================================================ */
.variant-section {
  padding: @spacing-lg @spacing-lg 0;
}

.variant-label {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  font-size: @font-size-sm;
  font-weight: @font-weight-semibold;
  color: @gray-300;
  margin-bottom: @spacing-md;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.variant-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: @spacing-md;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
}

.variant-card {
  padding: @spacing-md;
  border-radius: @radius-card;
  border: 1px solid @metal-border;
  background: rgba(255, 255, 255, 0.015);
  cursor: pointer;
  transition: all @transition-fast;
  position: relative;

  &:hover {
    transform: translateY(-2px);
    border-color: rgba(255, 255, 255, 0.12);
    box-shadow: @shadow-elevation-2;
  }

  &.active {
    border-color: var(--variant-color);
    box-shadow: @shadow-elevation-3;
    transform: translateY(-1px);

    &::after {
      content: '当前方案';
      position: absolute;
      top: @spacing-xs;
      right: @spacing-sm;
      font-size: @font-size-xs;
      font-weight: @font-weight-bold;
      color: #fff;
      background: var(--variant-color);
      padding: 1px 6px;
      border-radius: @radius-tag;
    }
  }
}

.variant-top {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  margin-bottom: @spacing-sm;
}

.variant-icon {
  font-size: 18px;
  line-height: 1;
  display: inline-flex;
  align-items: center;
}

.variant-name {
  font-size: @font-size-sm;
  font-weight: @font-weight-semibold;
  color: @gray-50;
}

.variant-intensity {
  margin-left: auto;
  font-size: @font-size-xs !important;
}

.variant-desc {
  font-size: @font-size-xs;
  color: @gray-400;
  line-height: @line-height-base;
  margin: 0 0 @spacing-sm;
}

.variant-stats {
  display: flex;
  gap: @spacing-sm;
  flex-wrap: wrap;
}

.vs-item {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: @font-size-xs;
  color: @gray-400;
}

.variant-highlights {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-top: @spacing-sm;
}

.highlight-tag {
  font-size: @font-size-xs;
  color: @gray-400;
  background: rgba(255, 255, 255, 0.04);
  padding: 1px 5px;
  border-radius: @radius-tag;
}

/*============================================================ */
/*工具栏（视图切换 + 图例） */
/*============================================================ */
.toolbar-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: @spacing-sm @spacing-lg;
  border-bottom: 1px solid @metal-border;
  flex-wrap: wrap;
  gap: @spacing-sm;
}

.view-tabs {
  display: flex;
  background: rgba(255, 255, 255, 0.02);
  border-radius: @radius-btn;
  padding: 2px;
}

.view-tab {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 5px 12px;
  border: none;
  background: transparent;
  border-radius: @radius-btn;
  font-size: @font-size-xs;
  color: @gray-400;
  cursor: pointer;
  transition: all @transition-fast;
  font-family: inherit;

  &.active {
    background: rgba(255, 255, 255, 0.06);
    color: @gray-50;
    font-weight: @font-weight-semibold;
  }

  &:hover:not(.active) {
    color: @gray-300;
  }
}

.legend-row {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  font-size: @font-size-xs;
  color: @gray-400;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  display: inline-block;
  cursor: help;
  transition: transform @transition-fast;

  &:hover {
    transform: scale(1.5);
  }
}

.legend-divider {
  color: @gray-400;
  font-size: @font-size-xs;
}

.legend-label {
  color: @gray-400;
  font-size: @font-size-xs;
  font-family: @font-family-mono;
}

/*============================================================ */
/*图表占位 */
/*============================================================ */
.chart-placeholder {
  min-height: 260px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: @gray-400;
  gap: @spacing-md;
  padding: @spacing-xl;
}

.empty-icon {
  font-size: 40px;
  color: @gray-400;
  opacity: 0.3;
}

.empty-text {
  font-size: @font-size-md;
  color: @gray-300;
  margin: 0;
  font-weight: @font-weight-medium;
}

.empty-hint {
  font-size: @font-size-sm;
  color: @gray-400;
  margin: 0;
}

/*============================================================ */
/*甘特图容器 */
/*============================================================ */
.gantt-wrap {
  padding: @spacing-xs 0;
  min-height: 260px;
}

.gantt-chart {
  width: 100%;
  min-height: 260px;
}

/*============================================================ */
/*时间轴 */
/*============================================================ */
.timeline-wrap {
  padding: @spacing-lg;
  min-height: 260px;
}

.timeline-list {
  position: relative;
  padding-left: 28px;
}

.timeline-line-track {
  position: absolute;
  left: 15px;
  top: 8px;
  bottom: 8px;
  width: 0;
  border-left: 1.5px dotted rgba(148, 163, 184, 0.25);
}

/*每日分组 */
.timeline-day-group {
  position: relative;
  margin-bottom: @spacing-xl;

  &:last-child {
    margin-bottom: 0;
  }
}

/*天数标记 */
.timeline-marker {
  display: flex;
  align-items: flex-start;
  gap: @spacing-md;
  padding-bottom: @spacing-sm;
}

.marker-dot {
  position: absolute;
  left: -19px;
  top: 5px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid #0a0d14;
  box-shadow: @shadow-elevation-1;
  z-index: 1;
}

.marker-content {
  flex: 1;
}

.marker-header {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  flex-wrap: wrap;
}

.day-number {
  font-size: @font-size-md;
  font-weight: @font-weight-bold;
  color: @gray-50;
}

.day-date {
  font-size: @font-size-xs;
  color: @gray-400;
  font-family: @font-family-mono;
}

/*任务列表 */
.timeline-tasks {
  display: flex;
  flex-direction: column;
  gap: @spacing-sm;
  margin-top: @spacing-sm;
}

.task-card {
  display: flex;
  background: rgba(255, 255, 255, 0.025);
  border-radius: @radius-card;
  border: 1px solid rgba(255, 255, 255, 0.06);
  overflow: visible;
  cursor: pointer;
  transition: all @transition-base;
  position: relative;

  &:hover {
    border-color: rgba(255, 255, 255, 0.12);
    background: rgba(255, 255, 255, 0.045);
    transform: translateX(4px);
  }

  &.is-tooltip-open {
    border-color: rgba(212, 163, 115, 0.3);
    z-index: 5;
  }
}

/*── Hover Tooltip ── */
.task-tooltip {
  position: absolute;
  left: calc(100% + 12px);
  top: 50%;
  transform: translateY(-50%);
  width: 280px;
  background: rgba(10, 13, 20, 0.95);
  border: 1px solid rgba(212, 163, 115, 0.2);
  border-radius: 6px;
  padding: 14px 16px;
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.6),
    0 0 0 1px rgba(0, 0, 0, 0.3);
  z-index: @z-tooltip;
  pointer-events: none;
}

.tt-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
}

.tt-label {
  color: @gray-400;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  font-size: 10px;
}

.tt-value {
  color: @gray-50;
  font-weight: 600;
  font-size: 12px;
}

.tt-kp {
  color: @brand-oat-300;
}

.tt-desc {
  font-size: 12px;
  color: @gray-300;
  line-height: 1.5;
  margin: 8px 0 10px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.tt-resources {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.tt-resource-label {
  font-size: 10px;
  color: @gray-400;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-bottom: 2px;
}

.tt-resource-item {
  font-size: 11px;
  color: @brand-cyan-400;
  padding: 2px 8px;
  background: rgba(0, 212, 255, 0.06);
  border-radius: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/*Tooltip 出入动画 */
.tooltip-fade-enter-active,
.tooltip-fade-leave-active {
  transition:
    opacity 150ms ease,
    transform 150ms ease;
}

.tooltip-fade-enter-from,
.tooltip-fade-leave-to {
  opacity: 0;
  transform: translateY(-50%) translateX(-8px);
}

.task-type-strip {
  width: 4px;
  flex-shrink: 0;
}

.task-body {
  flex: 1;
  padding: @spacing-sm @spacing-md;
  min-width: 0;
}

.task-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.task-duration {
  font-size: 11px;
  color: @gray-400;
  font-weight: @font-weight-medium;
}

.task-title {
  font-size: 13px;
  font-weight: @font-weight-semibold;
  color: @gray-50;
  margin: 0 0 4px;
  line-height: @line-height-base;
}

.task-meta {
  font-size: 11px;
  color: @gray-400;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.task-kp {
  color: @brand-cyan-400;
}

.task-diff {
  display: flex;
  align-items: center;
  gap: 2px;
}

.diff-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

/*============================================================ */
/*底部汇总 */
/*============================================================ */
.summary-bar {
  display: flex;
  align-items: center;
  gap: @spacing-xl;
  padding: @spacing-md @spacing-lg;
  border-top: 1px solid @metal-border;
  flex-wrap: wrap;

  @media (max-width: 640px) {
    gap: @spacing-md;
  }
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-label {
  font-size: @font-size-xs;
  color: @gray-400;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.summary-value {
  font-size: @font-size-sm;
  font-weight: @font-weight-semibold;
  color: @gray-50;
  font-family: @font-family-mono;
}

.load-value {
  &.load-low {
    color: @color-success;
  }
  &.load-mid {
    color: @color-warning;
  }
  &.load-high {
    color: @color-error;
  }
}

/*============================================================ */
/*响应式 */
/*============================================================ */
@media (max-width: 768px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }

  .toolbar-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .variant-row {
    grid-template-columns: 1fr;
  }

  .timeline-list {
    padding-left: 22px;
  }

  .marker-dot {
    left: -15px;
    width: 10px;
    height: 10px;
  }

  .summary-bar {
    gap: @spacing-md;
  }

  /*移动端任务卡片不再预留浮层空间 */
  .task-card.is-tooltip-open {
    z-index: auto;
  }
}
</style>

<!-- Bottom Sheet 通过 Teleport 挂到 body，样式需非 scoped -->
<style lang="less">
@import '@/assets/styles/variables.less';

.task-sheet-mask {
  position: fixed;
  inset: 0;
  z-index: 1200;
  background: rgba(6, 9, 16, 0.62);
  backdrop-filter: blur(2px);
}

.task-sheet {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1201;
  max-height: 76vh;
  overflow-y: auto;
  padding: 8px 16px calc(16px + env(safe-area-inset-bottom));
  border-radius: 16px 16px 0 0;
  background: rgba(20, 27, 43, 0.98);
  border-top: 1px solid rgba(212, 163, 115, 0.22);
  box-shadow: 0 -10px 32px rgba(0, 0, 0, 0.5);
  -webkit-overflow-scrolling: touch;

  .sheet-handle {
    width: 38px;
    height: 4px;
    margin: 0 auto 12px;
    border-radius: 2px;
    background: rgba(255, 255, 255, 0.22);
  }

  .sheet-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
  }

  .sheet-title {
    margin: 0;
    color: #f8fafc;
    font-size: 15px;
    font-weight: 600;
    line-height: 1.45;
  }

  .sheet-close {
    flex-shrink: 0;
    width: 28px;
    height: 28px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.08);
    color: #94a3b8;
    cursor: pointer;

    &:active {
      background: rgba(255, 255, 255, 0.16);
    }
  }

  .sheet-body {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .tt-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    font-size: 13px;
  }

  .tt-label {
    flex-shrink: 0;
    width: 60px;
    color: #94a3b8;
  }

  .tt-value {
    color: #e2e8f0;
    word-break: break-all;
  }

  .tt-kp {
    color: #d4a373;
    font-weight: 600;
  }

  .tt-desc {
    margin: 4px 0 0;
    color: #cbd5e1;
    font-size: 12px;
    line-height: 1.7;
  }

  .tt-resources {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    margin-top: 6px;
  }

  .tt-resource-label {
    color: #94a3b8;
    font-size: 12px;
  }

  .tt-resource-item {
    padding: 2px 8px;
    border-radius: 10px;
    background: rgba(79, 124, 255, 0.14);
    color: #7aa2ff;
    font-size: 12px;
  }

  .sheet-action {
    width: 100%;
    margin-top: 16px;
    padding: 11px 0;
    border: none;
    border-radius: 10px;
    background: linear-gradient(135deg, #d4a373, #b8875a);
    color: #10131a;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;

    &:active {
      opacity: 0.85;
    }
  }
}

/* 过渡动画 */
.sheet-fade-enter-active,
.sheet-fade-leave-active {
  transition: opacity 0.22s ease;
}
.sheet-fade-enter-from,
.sheet-fade-leave-to {
  opacity: 0;
}

.sheet-slide-enter-active,
.sheet-slide-leave-active {
  transition: transform 0.26s cubic-bezier(0.22, 1, 0.36, 1);
}
.sheet-slide-enter-from,
.sheet-slide-leave-to {
  transform: translateY(100%);
}
</style>
