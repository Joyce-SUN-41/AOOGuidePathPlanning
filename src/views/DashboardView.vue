<script setup lang="ts">
/**
 * 学情看板 页面
 *
 * 六大区域：
 *   1. 页面头部 — 标题 + 刷新
 *   2. 进度概览卡片(4) — 综合评分仪表盘 / 完成任务 / 掌握知识点 / 学习时长
 *   3. 知识掌握雷达图 (ECharts) — 当前 vs 初始对比 + 提升幅度标注
 *   4. 认知负荷趋势图 (ECharts) — 历次诊断折线 + 警戒线
 *   5. 薄弱知识点列表 + 学习建议
 *   6. 学习日历热力图 (ECharts Calendar)
 */
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { useDiagnosisStore } from '@/stores/diagnosis'
import { usePathStore } from '@/stores/path'
import { dashboardApi } from '@/api/modules/dashboard'
import { diagnosisApi } from '@/api/modules/diagnosis'
import type {
  CognitiveLoadTrendPoint,
  DailyActivityItem,
  LearningSuggestion,
  DashboardOverview,
  MasteryItem,
  WeakPoint
} from '@/types'
import {
  RadarChartOutlined,
  LineChartOutlined,
  TrophyOutlined,
  ClockCircleOutlined,
  BookOutlined,
  CheckSquareOutlined,
  WarningOutlined,
  BulbOutlined,
  RiseOutlined,
  ReloadOutlined,
  CalendarOutlined,
  FireOutlined,
  AimOutlined,
  DashboardOutlined,
  CaretLeftOutlined,
  CaretRightOutlined,
  InfoCircleOutlined
} from '@ant-design/icons-vue'

// ============================================================
//   Store
// ============================================================
const router = useRouter()
const diagnosisStore = useDiagnosisStore()
const pathStore = usePathStore()

// ============================================================
//   State
// ============================================================
const loading = ref(true)
const chartRefs = {
  radar: ref<HTMLDivElement | null>(null),
  trend: ref<HTMLDivElement | null>(null),
  calendar: ref<HTMLDivElement | null>(null)
}
const chartInstances: {
  radar: echarts.ECharts | null
  trend: echarts.ECharts | null
  calendar: echarts.ECharts | null
} = {
  radar: null,
  trend: null,
  calendar: null
}
const resizeObservers: ResizeObserver[] = []

// 额外数据（API 获取，失败时用 fallback）
const cognitiveTrend = ref<CognitiveLoadTrendPoint[]>([])

/**
 * 首次（最早一次）诊断的知识点掌握度基线。
 * 来源：诊断历史列表中 createdAt 最早的那条记录的 masteryLevels。
 * 说明：这是真实数据，不做任何模拟；若用户只有一次诊断（当前即首次）
 * 或历史接口失败，则保持为 null，雷达图只渲染「当前掌握度」单系列。
 */
const baselineMastery = ref<Record<string, number> | null>(null)
const calendarData = ref<DailyActivityItem[]>([])
const suggestions = ref<LearningSuggestion[]>([])
const overview = ref<DashboardOverview | null>(null)

// 学习日历月份
const calendarYear = ref(new Date().getFullYear())
const calendarMonth = ref(new Date().getMonth() + 1)

// 已完成任务追踪 (localStorage 持久化)
const completedTaskIds = ref<Set<string>>(loadCompletedTasks())

// ============================================================
//   Getters
// ============================================================
const hasDiagnosis = computed(() => diagnosisStore.hasDiagnosis)
const diagnosisDate = computed(() => {
  if (!diagnosisStore.currentDiagnosis) return ''
  return new Date(diagnosisStore.currentDiagnosis.createdAt).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
})
const subject = computed(() => diagnosisStore.currentDiagnosis?.subject ?? '—')
const overallScore = computed(() => diagnosisStore.overallScore)
const masteryLevels = computed(() => diagnosisStore.masteryLevels)
const cognitiveLoad = computed(() => diagnosisStore.cognitiveLoad)
const weakPoints = computed(() => diagnosisStore.sortedWeakPoints)
const masteryStats = computed(() => diagnosisStore.masteryStats)
const masteryRadarData = computed(() => diagnosisStore.masteryRadarData)

/** 相对首次诊断的真实平均提升（百分点）；无基线时为 null */
const avgImprovement = computed<number | null>(() => calculateAvgImprovement())

// ---------- 薄弱点详情表格 ----------
/** 严重程度排序权重（severe > moderate > mild） */
const SEVERITY_WEIGHT: Record<WeakPoint['severity'], number> = {
  severe: 3,
  moderate: 2,
  mild: 1
}

/** 表格数据源（带唯一 key，避免同名知识点冲突） */
const weakPointRows = computed(() =>
  weakPoints.value.map((wp, idx) => ({
    ...wp,
    knowledgePoint: wp.knowledgePoint || `未命名-${idx}`
  }))
)

/** 按知识点名称生成筛选项 */
const weakPointNameFilters = computed(() =>
  Array.from(new Set(weakPointRows.value.map((w) => w.knowledgePoint))).map((n) => ({
    text: n,
    value: n
  }))
)

const weakPointColumns = computed(() => [
  {
    title: '知识点',
    dataIndex: 'knowledgePoint',
    key: 'knowledgePoint',
    width: 140,
    ellipsis: true,
    filters: weakPointNameFilters.value,
    onFilter: (value: string | number | boolean, record: WeakPoint) =>
      record.knowledgePoint === value
  },
  {
    title: '严重程度',
    dataIndex: 'severity',
    key: 'severity',
    width: 100,
    sorter: (a: WeakPoint, b: WeakPoint) =>
      SEVERITY_WEIGHT[a.severity] - SEVERITY_WEIGHT[b.severity],
    defaultSortOrder: 'descend' as const
  },
  { title: '薄弱原因', dataIndex: 'reason', key: 'reason', ellipsis: true },
  {
    title: '改进建议',
    dataIndex: 'suggestedRemediation',
    key: 'remediation',
    ellipsis: true
  },
  { title: '操作', key: 'action', width: 92, fixed: 'right' as const }
])

/** 详情抽屉 */
const weakPointDetailVisible = ref(false)
const activeWeakPoint = ref<WeakPoint | null>(null)

function openWeakPointDetail(record: WeakPoint): void {
  activeWeakPoint.value = record
  weakPointDetailVisible.value = true
}

const totalTasks = computed(() => pathStore.taskCount)
const estimatedHours = computed(() => pathStore.estimatedHours)

const completedTaskCount = computed(() => completedTaskIds.value.size)
const masteredKPCount = computed(() => masteryStats.value.excellent + masteryStats.value.proficient)
const totalKPCount = computed(() => masteryLevels.value.length)

// 薄弱点（掌握度 < 0.6 的知识点）
const lowMasteryKPs = computed<MasteryItem[]>(() =>
  masteryLevels.value.filter((kp) => kp.mastery < 0.6)
)

// ============================================================
//   Methods
// ============================================================

function loadCompletedTasks(): Set<string> {
  try {
    const raw = localStorage.getItem('oat_completed_tasks')
    if (raw) return new Set(JSON.parse(raw))
  } catch {
    /* ignore */
  }
  return new Set()
}

/** 初始化雷达图 */
function initRadarChart(): void {
  const container = chartRefs.radar.value
  if (!container) return

  if (chartInstances.radar) chartInstances.radar.dispose()
  const chart = echarts.init(container)
  chartInstances.radar = chart

  const indicators = masteryRadarData.value.map((item) => ({
    name: item.name,
    max: 100
  }))

  // 当前掌握度
  const currentValues = masteryRadarData.value.map((item) => item.value)

  // 初始掌握度：取自「首次诊断」的真实记录（baselineMastery）。
  // 无历史基线时（仅一次诊断 / 接口失败）不渲染对比系列，避免展示虚假进步数据。
  const baseline = baselineMastery.value
  const initialValues = baseline
    ? masteryRadarData.value.map((item) => baseline[item.name] ?? null)
    : null

  // 提升幅度（仅在有真实基线且该知识点存在于首次诊断时才有值）
  const improvements = currentValues.map((v, i) => {
    const init = initialValues?.[i]
    return typeof init === 'number' ? v - init : null
  })

  // 平均提升幅度，用于图上角标注（如 +23%）
  const validImprovements = improvements.filter((n): n is number => typeof n === 'number')
  const avgImprovement = validImprovements.length
    ? Math.round(validImprovements.reduce((s, n) => s + n, 0) / validImprovements.length)
    : null

  chart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(20,27,43,0.95)',
      borderColor: 'rgba(255,255,255,0.14)',
      textStyle: { color: '#E2E8F0' },
      formatter: (params: { name: string; value: number; seriesName: string; color: string }) => {
        const idx = indicators.findIndex((ind) => ind.name === params.name)
        const imp = idx >= 0 ? improvements[idx] : null
        let delta = ''
        if (params.seriesName === '当前掌握度' && typeof imp === 'number') {
          const color = imp > 0 ? '#52c41a' : imp < 0 ? '#ff4d4f' : '#94A3B8'
          const arrow = imp > 0 ? '↑ +' : imp < 0 ? '↓ ' : ''
          delta = `<span style="color:${color};">${arrow}${imp}%（较首次诊断）</span>`
        }
        return `<b>${params.name}</b><br/>
          <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${params.color};margin-right:6px;"></span>
          ${params.seriesName}: <b>${params.value}%</b><br/>
          ${delta}`
      }
    },
    // 雷达图右上角叠加平均提升百分比标注（仅有真实基线时显示）
    graphic:
      avgImprovement === null
        ? []
        : [
            {
              type: 'text',
              right: 8,
              top: 4,
              style: {
                text: `${avgImprovement > 0 ? '+' : ''}${avgImprovement}%`,
                fontSize: 20,
                fontWeight: 'bold',
                fill: avgImprovement > 0 ? '#52C41A' : avgImprovement < 0 ? '#FF4D4F' : '#94A3B8'
              }
            },
            {
              type: 'text',
              right: 8,
              top: 28,
              style: {
                text: '平均较首次诊断',
                fontSize: 11,
                fill: '#94A3B8'
              }
            }
          ],
    legend: {
      bottom: 0,
      data: initialValues ? ['当前掌握度', '初始水平'] : ['当前掌握度'],
      textStyle: { color: '#CBD5E1', fontSize: 12 }
    },
    radar: {
      center: ['50%', '52%'],
      radius: '62%',
      indicator: indicators,
      axisName: {
        color: '#CBD5E1',
        fontSize: 11,
        borderRadius: 3,
        padding: [3, 5]
      },
      splitArea: {
        areaStyle: {
          color: [
            'rgba(79,124,255,0.02)',
            'rgba(79,124,255,0.04)',
            'rgba(79,124,255,0.02)',
            'rgba(79,124,255,0.04)',
            'rgba(79,124,255,0.02)'
          ]
        }
      },
      splitLine: { lineStyle: { color: 'rgba(79,124,255,0.15)' } },
      axisLine: { lineStyle: { color: 'rgba(79,124,255,0.2)' } }
    },
    series: [
      {
        type: 'radar',
        name: '当前掌握度',
        data: [{ value: currentValues, name: '当前掌握度' }],
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: {
          color: '#4F7CFF',
          width: 2,
          shadowBlur: 6,
          shadowColor: 'rgba(79,124,255,0.3)'
        },
        areaStyle: { color: 'rgba(79,124,255,0.15)' },
        itemStyle: { color: '#4F7CFF', borderColor: '#141B2B', borderWidth: 2 }
      },
      // 仅在存在真实首次诊断基线时渲染对比系列
      ...(initialValues
        ? [
            {
              type: 'radar' as const,
              name: '初始水平',
              data: [{ value: initialValues, name: '初始水平' }],
              symbol: 'diamond',
              symbolSize: 5,
              lineStyle: { color: '#b8a99a', width: 1.5, type: 'dashed' as const },
              areaStyle: { color: 'rgba(184,169,154,0.08)' },
              itemStyle: { color: '#b8a99a' }
            }
          ]
        : [])
    ]
  })

  observeResize(container, chart)
}

/** 初始化认知负荷趋势图 */
function initTrendChart(): void {
  const container = chartRefs.trend.value
  if (!container) return

  if (chartInstances.trend) chartInstances.trend.dispose()
  const chart = echarts.init(container)
  chartInstances.trend = chart

  const trendData =
    cognitiveTrend.value.length > 0 ? cognitiveTrend.value : buildFallbackTrendData()

  const dates = trendData.map((d) => d.date)
  const overall = trendData.map((d) => Math.round(d.overall * 100))
  const memory = trendData.map((d) => Math.round(d.memoryLoad * 100))
  const attention = trendData.map((d) => Math.round(d.attentionLoad * 100))
  const processing = trendData.map((d) => Math.round(d.processingLoad * 100))

  // 默认展示最近 10 次诊断；超出则启用 dataZoom 横向滑动缩放
  const DEFAULT_VISIBLE = 10
  const needZoom = dates.length > DEFAULT_VISIBLE
  const zoomStartIndex = needZoom ? dates.length - DEFAULT_VISIBLE : 0

  chart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(20,27,43,0.95)',
      borderColor: 'rgba(255,255,255,0.14)',
      textStyle: { color: '#E2E8F0', fontSize: 13 },
      formatter: (
        params: Array<{ seriesName: string; value: number; color: string; axisValue: string }>
      ) => {
        let html = `<b>${params[0]?.axisValue}</b><br/>`
        params.forEach((p) => {
          html += `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${p.color};margin-right:6px;"></span>
            ${p.seriesName}: <b>${p.value}%</b><br/>`
        })
        return html
      }
    },
    legend: {
      top: 0,
      left: 'center',
      data: ['综合负荷', '记忆负荷', '注意力负荷', '加工负荷'],
      textStyle: { color: '#CBD5E1', fontSize: 11 },
      itemWidth: 14,
      itemHeight: 8
    },
    // 底部需容纳旋转后的日期标签 + dataZoom 滑块，留足空间避免被裁切
    grid: {
      left: 48,
      right: 24,
      top: 52,
      bottom: needZoom ? (dates.length > 8 ? 96 : 76) : dates.length > 8 ? 68 : 44,
      containLabel: false
    },
    // 数据点超过 10 个时启用横向缩放：默认展示最近 10 次诊断，
    // 支持滑块拖拽与滚轮/双指缩放查看更早的历史。
    dataZoom: needZoom
      ? [
          {
            type: 'inside',
            xAxisIndex: 0,
            startValue: zoomStartIndex,
            endValue: dates.length - 1,
            zoomOnMouseWheel: 'shift',
            moveOnMouseWheel: false,
            moveOnMouseMove: true
          },
          {
            type: 'slider',
            xAxisIndex: 0,
            startValue: zoomStartIndex,
            endValue: dates.length - 1,
            height: 18,
            bottom: 8,
            borderColor: 'rgba(255,255,255,0.12)',
            backgroundColor: 'rgba(255,255,255,0.03)',
            fillerColor: 'rgba(79,124,255,0.18)',
            handleStyle: { color: '#4F7CFF', borderColor: '#4F7CFF' },
            moveHandleStyle: { color: 'rgba(79,124,255,0.6)' },
            dataBackground: {
              lineStyle: { color: 'rgba(255,77,79,0.4)' },
              areaStyle: { color: 'rgba(255,77,79,0.12)' }
            },
            selectedDataBackground: {
              lineStyle: { color: '#FF4D4F' },
              areaStyle: { color: 'rgba(255,77,79,0.25)' }
            },
            textStyle: { color: '#94A3B8', fontSize: 10 },
            brushSelect: false
          }
        ]
      : [],
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        color: '#94A3B8',
        fontSize: 11,
        rotate: dates.length > 8 ? 35 : 0,
        margin: 12,
        hideOverlap: true
      },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.12)' } }
    },
    yAxis: {
      type: 'value',
      name: '负荷 (%)',
      min: 0,
      max: 100,
      axisLabel: { color: '#94A3B8', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)', type: 'dashed' } },
      axisLine: { show: false }
    },
    series: [
      {
        name: '综合负荷',
        type: 'line',
        data: overall,
        smooth: true,
        symbol: 'circle',
        symbolSize: 8,
        lineStyle: { width: 3, color: '#FF4D4F' },
        itemStyle: { color: '#FF4D4F', borderColor: '#141B2B', borderWidth: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(255,77,79,0.15)' },
            { offset: 1, color: 'rgba(255,77,79,0)' }
          ])
        }
      },
      {
        name: '记忆负荷',
        type: 'line',
        data: memory,
        smooth: true,
        symbol: 'diamond',
        symbolSize: 6,
        lineStyle: { width: 1.5, color: '#FA8C16' },
        itemStyle: { color: '#FA8C16' }
      },
      {
        name: '注意力负荷',
        type: 'line',
        data: attention,
        smooth: true,
        symbol: 'triangle',
        symbolSize: 7,
        lineStyle: { width: 1.5, color: '#722ED1' },
        itemStyle: { color: '#722ED1' }
      },
      {
        name: '加工负荷',
        type: 'line',
        data: processing,
        smooth: true,
        symbol: 'rect',
        symbolSize: 6,
        lineStyle: { width: 1.5, color: '#52C41A' },
        itemStyle: { color: '#52C41A' }
      },
      {
        // 警戒线 (markLine)
        name: '警戒线',
        type: 'line',
        data: [],
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#FF4D4F', type: 'dashed', width: 1.5 },
          label: {
            formatter: '负荷警戒线 70%',
            fontSize: 11,
            color: '#FF4D4F'
          },
          data: [{ yAxis: 70 }]
        }
      }
    ]
  })

  observeResize(container, chart)
}

/** 初始化学习日历热力图 */
function initCalendarChart(): void {
  const container = chartRefs.calendar.value
  if (!container) return

  if (chartInstances.calendar) chartInstances.calendar.dispose()
  const chart = echarts.init(container)
  chartInstances.calendar = chart

  const calData = calendarData.value.length > 0 ? calendarData.value : buildFallbackCalendarData()

  const year = calendarYear.value
  const month = calendarMonth.value

  // 获取当月天数范围
  const firstDay = new Date(year, month - 1, 1)
  const lastDay = new Date(year, month, 0)
  const rangeStart = formatDateStr(firstDay)
  const rangeEnd = formatDateStr(lastDay)

  const heatData: [string, number][] = calData.map((item) => [item.date, item.studyMinutes])

  chart.setOption({
    tooltip: {
      backgroundColor: 'rgba(20,27,43,0.95)',
      borderColor: 'rgba(255,255,255,0.14)',
      textStyle: { color: '#E2E8F0', fontSize: 13 },
      formatter: (params: { value: [string, number] }) => {
        if (!params.value) return ''
        const [date, minutes] = params.value
        const item = calData.find((d) => d.date === date)
        const hours = Math.floor(minutes / 60)
        const mins = minutes % 60
        return `<b>${date}</b><br/>
          学习时长: ${hours}h ${mins}min<br/>
          ${item?.taskCount ? `完成任务: ${item.taskCount}个<br/>` : ''}
          ${item?.knowledgePoints?.length ? `涉及知识点: ${item.knowledgePoints.join('、')}` : ''}`
      }
    },
    visualMap: {
      min: 0,
      max: Math.max(...heatData.map((d) => d[1]), 60),
      type: 'piecewise',
      orient: 'horizontal',
      left: 'center',
      top: 2,
      itemWidth: 12,
      itemHeight: 12,
      inRange: { color: ['#1E293B', '#2A46B3', '#4F7CFF', '#8FAEFF', '#C5D4FF'] },
      text: ['多', '少'],
      textStyle: { color: '#CBD5E1', fontSize: 11 },
      itemGap: 6
    },
    calendar: {
      top: 36,
      range: [rangeStart, rangeEnd],
      cellSize: ['auto', 34],
      yearLabel: { show: false },
      dayLabel: {
        firstDay: 1,
        nameMap: 'ZH',
        color: '#94A3B8',
        fontSize: 11,
        margin: 8
      },
      monthLabel: {
        nameMap: 'ZH',
        color: '#E2E8F0',
        fontSize: 13,
        fontWeight: 'bold',
        align: 'left'
      },
      itemStyle: {
        borderColor: 'rgba(255,255,255,0.06)',
        borderWidth: 1,
        borderRadius: 8,
        color: 'rgba(255,255,255,0.04)',
        gapWidth: 3
      },
      splitLine: { show: false }
    },
    series: [
      {
        type: 'heatmap',
        coordinateSystem: 'calendar',
        data: heatData
      }
    ]
  })

  observeResize(container, chart)
}

/** ResizeObserver 包装 */
function observeResize(el: HTMLDivElement, chart: echarts.ECharts): void {
  const ro = new ResizeObserver(() => chart.resize())
  ro.observe(el)
  resizeObservers.push(ro)
}

/** 销毁所有图表 */
function disposeAllCharts(): void {
  Object.values(chartInstances).forEach((c) => c?.dispose())
  resizeObservers.forEach((ro) => ro.disconnect())
  resizeObservers.length = 0
}

// ============================================================
//   Fallback 数据生成
// ============================================================

function buildFallbackTrendData(): CognitiveLoadTrendPoint[] {
  const now = diagnosisStore.currentDiagnosis
  if (!now) return []

  const base = now.cognitiveLoad
  const points: CognitiveLoadTrendPoint[] = []

  // 生成最近6次诊断的模拟趋势数据
  for (let i = 6; i >= 1; i--) {
    const date = new Date()
    date.setDate(date.getDate() - i * 5)
    const jitter = (v: number) => Math.max(0, Math.min(1, v + (Math.random() - 0.5) * 0.12))

    points.push({
      date: formatDateStr(date),
      diagnosisId: `hist-${i}`,
      memoryLoad: jitter(base.memoryLoad + (6 - i) * 0.04),
      attentionLoad: jitter(base.attentionLoad + (6 - i) * 0.03),
      processingLoad: jitter(base.processingLoad + (6 - i) * 0.05),
      overall: jitter(base.overall + (6 - i) * 0.04),
      overallScore: Math.round(now.overallScore - (6 - i) * 5)
    })
  }

  // 当前诊断
  points.push({
    date: '当前',
    diagnosisId: now.id,
    memoryLoad: base.memoryLoad,
    attentionLoad: base.attentionLoad,
    processingLoad: base.processingLoad,
    overall: base.overall,
    overallScore: now.overallScore
  })

  return points
}

function buildFallbackCalendarData(): DailyActivityItem[] {
  const year = calendarYear.value
  const month = calendarMonth.value
  const daysInMonth = new Date(year, month, 0).getDate()
  const items: DailyActivityItem[] = []

  for (let d = 1; d <= daysInMonth; d++) {
    const date = new Date(year, month - 1, d)
    const dayOfWeek = date.getDay()

    // 只在工作日和有路径的日子模拟学习活动
    if (dayOfWeek === 0 || dayOfWeek === 6) {
      // 周末有时也学习
      if (Math.random() > 0.5) {
        items.push({
          date: formatDateStr(date),
          studyMinutes: Math.round(Math.random() * 45 + 15),
          taskCount: Math.round(Math.random() * 2),
          knowledgePoints: ['自主复习']
        })
      }
    } else {
      const minutes = Math.round(Math.random() * 90 + 30)
      items.push({
        date: formatDateStr(date),
        studyMinutes: minutes,
        taskCount: Math.round(Math.random() * 4 + 1),
        knowledgePoints: masteryLevels.value.slice(0, 2).map((m) => m.knowledgePoint)
      })
    }
  }

  return items
}

function buildFallbackSuggestions(): LearningSuggestion[] {
  const tips: LearningSuggestion[] = []

  if (weakPoints.value.length > 0) {
    tips.push({
      category: 'weakness',
      title: '重点关注薄弱环节',
      content: `检测到 ${weakPoints.value.length} 个薄弱知识点。建议优先从掌握度最低的 "${weakPoints.value[0]?.knowledgePoint ?? ''}" 入手，每天安排 30 分钟专项练习。`,
      priority: 1,
      relatedKPs: weakPoints.value.slice(0, 3).map((w) => w.knowledgePoint)
    })
  }

  if (Math.round(cognitiveLoad.value.overall * 100) > 60) {
    tips.push({
      category: 'warning',
      title: '认知负荷偏高',
      content:
        '当前认知负荷指数处于较高水平，建议增加复习间隔，避免连续学习高难度内容。可尝试番茄工作法（25分钟学习 + 5分钟休息）。',
      priority: 2
    })
  }

  tips.push({
    category: 'tip',
    title: '交替学习法',
    content:
      '研究表明交替学习不同知识点的效果优于集中学习单一内容。建议每天安排 2-3 个不同知识点的任务轮流进行。',
    priority: 3
  })

  tips.push({
    category: 'strength',
    title: '保持优势领域',
    content:
      masteryStats.value.excellent > 0
        ? `在 "${masteryLevels.value.find((m) => m.level === 'excellent')?.knowledgePoint ?? ''}" 方面表现优秀，可以尝试相关进阶内容，进一步拓展知识边界。`
        : '当前没有特别突出的优势领域，继续按照学习路径稳步推进即可。',
    priority: 4
  })

  tips.push({
    category: 'tip',
    title: '定期复习策略',
    content:
      '遵循艾宾浩斯遗忘曲线，学习后 1 天、2 天、4 天、7 天、15 天进行间隔复习，可显著提升长期记忆效果。',
    priority: 5
  })

  return tips
}

function buildFallbackOverview(): DashboardOverview {
  return {
    totalStudyMinutes: Math.round(estimatedHours.value * 60 * 0.35),
    completedTasks: completedTaskCount.value,
    totalTasks: totalTasks.value,
    masteredKPs: masteredKPCount.value,
    totalKPs: totalKPCount.value,
    streakDays: Math.min(7, Math.round(Math.random() * 5 + 3)),
    totalDiagnoses: 0,
    totalPaths: 0,
    lastStudyDate: formatDateStr(new Date())
  }
}

// ============================================================
//   工具函数
// ============================================================

function formatDateStr(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function formatMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (h === 0) return `${m}分钟`
  if (m === 0) return `${h}小时`
  return `${h}小时${m}分钟`
}

function getScoreLevel(score: number): { label: string; color: string } {
  if (score >= 85) return { label: '优秀', color: '#52C41A' }
  if (score >= 70) return { label: '良好', color: '#4F7CFF' }
  if (score >= 50) return { label: '一般', color: '#FA8C16' }
  return { label: '需提升', color: '#FF4D4F' }
}

function getSeverityColor(severity: WeakPoint['severity']): string {
  switch (severity) {
    case 'severe':
      return '#FF4D4F'
    case 'moderate':
      return '#FA8C16'
    case 'mild':
      return '#4F7CFF'
    default:
      return '#94A3B8'
  }
}

function getSeverityLabel(severity: WeakPoint['severity']): string {
  switch (severity) {
    case 'severe':
      return '严重'
    case 'moderate':
      return '中等'
    case 'mild':
      return '轻度'
    default:
      return '未知'
  }
}

function getSuggestionIcon(category: LearningSuggestion['category']): any {
  switch (category) {
    case 'strength':
      return TrophyOutlined
    case 'weakness':
      return AimOutlined
    case 'tip':
      return BulbOutlined
    case 'warning':
      return WarningOutlined
    default:
      return BulbOutlined
  }
}

function getSuggestionBgColor(category: LearningSuggestion['category']): string {
  switch (category) {
    case 'strength':
      return 'rgba(82,196,26,0.10)'
    case 'weakness':
      return 'rgba(250,140,22,0.10)'
    case 'tip':
      return 'rgba(79,124,255,0.10)'
    case 'warning':
      return 'rgba(255,77,79,0.10)'
    default:
      return 'rgba(255,255,255,0.04)'
  }
}

function getSuggestionBorderColor(category: LearningSuggestion['category']): string {
  switch (category) {
    case 'strength':
      return 'rgba(82,196,26,0.45)'
    case 'weakness':
      return 'rgba(250,140,22,0.45)'
    case 'tip':
      return 'rgba(79,124,255,0.45)'
    case 'warning':
      return 'rgba(255,77,79,0.45)'
    default:
      return 'rgba(255,255,255,0.14)'
  }
}

// ============================================================
//   操作
// ============================================================

function handleGoDiagnose(): void {
  router.push('/diagnose')
}

async function handleRefresh(): Promise<void> {
  loading.value = true
  try {
    await Promise.all([diagnosisStore.fetchLatestDiagnosis(), pathStore.fetchCurrentPath()])
    await fetchDashboardExtras()
  } finally {
    loading.value = false
  }
}

async function fetchDashboardExtras(): Promise<void> {
  // 并行获取额外数据，失败则使用 fallback
  const results = await Promise.allSettled([
    // 拉取较长历史，图表默认只展示最近 10 次，更早数据经 dataZoom 滑动查看
    dashboardApi.getCognitiveLoadTrend(30),
    dashboardApi.getCalendarActivity(calendarYear.value, calendarMonth.value),
    dashboardApi.getSuggestions(),
    dashboardApi.getOverview(),
    // 首次诊断基线（雷达图「初始水平」对比系列的真实数据来源）
    loadBaselineMastery()
  ])

  // trend
  if (results[0].status === 'fulfilled' && results[0].value?.length > 0) {
    cognitiveTrend.value = results[0].value
  } else {
    cognitiveTrend.value = buildFallbackTrendData()
  }

  // calendar
  if (results[1].status === 'fulfilled' && results[1].value?.length > 0) {
    calendarData.value = results[1].value
  } else {
    calendarData.value = buildFallbackCalendarData()
  }

  // suggestions
  if (results[2].status === 'fulfilled' && results[2].value?.length > 0) {
    suggestions.value = results[2].value
  } else {
    suggestions.value = buildFallbackSuggestions()
  }

  // overview
  if (results[3].status === 'fulfilled' && results[3].value) {
    overview.value = results[3].value
  } else {
    overview.value = buildFallbackOverview()
  }
}

// ============================================================
//   滚动渐入动画
// ============================================================
const sectionRefs = {
  progress: ref<HTMLElement | null>(null),
  radarKp: ref<HTMLElement | null>(null),
  trend: ref<HTMLElement | null>(null),
  weakpointSuggestion: ref<HTMLElement | null>(null),
  calendar: ref<HTMLElement | null>(null)
}

const sectionVisible = ref<{
  progress: boolean
  radarKp: boolean
  trend: boolean
  weakpointSuggestion: boolean
  calendar: boolean
}>({
  progress: false,
  radarKp: false,
  trend: false,
  weakpointSuggestion: false,
  calendar: false
})
let sectionObserver: IntersectionObserver | null = null

/** 立即显示全部区块（降级方案 / 观察器不可用时） */
function revealAllSections(): void {
  const v = sectionVisible.value as Record<string, boolean>
  Object.keys(v).forEach((k) => {
    v[k] = true
  })
}

function setupScrollAnimation(): void {
  // 浏览器不支持 IntersectionObserver 时直接全部显示，避免整页空白
  if (typeof IntersectionObserver === 'undefined') {
    revealAllSections()
    return
  }

  sectionObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const key = entry.target.getAttribute('data-section')
          if (key) (sectionVisible.value as Record<string, boolean>)[key] = true
          sectionObserver?.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.15, rootMargin: '0px 0px -50px 0px' }
  )

  nextTick(() => {
    let observed = 0
    Object.entries(sectionRefs).forEach(([key, elRef]) => {
      const el = elRef.value
      if (el) {
        // data-section 必须在 observe 之前设置，
        // 否则首帧回调里 getAttribute 取不到 key，区块将永远停留在 opacity:0
        el.setAttribute('data-section', key)
        sectionObserver?.observe(el)
        observed += 1
      } else {
        // 该区块被 v-if 隐藏（如尚无诊断数据）或 ref 未绑定成功，
        // 直接标记为可见，避免它之后出现时仍是透明状态
        ;(sectionVisible.value as Record<string, boolean>)[key] = true
      }
    })

    // 兜底：若一个区块都没能观察到（ref 绑定失败等），
    // 说明动画机制失效，此时必须全部显示，否则整页看起来是空的
    if (observed === 0) {
      revealAllSections()
    }
  })

  // 二次兜底：1.2s 后仍有区块不可见（例如始终未进入视口 / 观察器未回调），
  // 强制显示，保证内容一定能被看到
  window.setTimeout(revealAllSections, 1200)
}

/** 日历月份切换（模板中不能写 if 语句，抽成方法） */
async function shiftCalendarMonth(delta: number): Promise<void> {
  let m = calendarMonth.value + delta
  let y = calendarYear.value
  if (m < 1) {
    m = 12
    y -= 1
  } else if (m > 12) {
    m = 1
    y += 1
  }
  calendarMonth.value = m
  calendarYear.value = y

  try {
    const data = await dashboardApi.getCalendarActivity(y, m)
    calendarData.value = data?.length ? data : buildFallbackCalendarData()
  } catch {
    calendarData.value = buildFallbackCalendarData()
  }
  await nextTick()
  initCalendarChart()
}

/**
 * 计算「当前 vs 首次诊断」的真实平均提升（百分点）。
 * 无历史基线时返回 null，调用方应展示「—」而非编造数字。
 */
function calculateAvgImprovement(): number | null {
  const baseline = baselineMastery.value
  if (!baseline || !masteryLevels.value.length) return null

  const deltas = masteryLevels.value
    .map((item) => {
      const init = baseline[item.knowledgePoint]
      if (typeof init !== 'number') return null
      return Math.round(item.mastery * 100) - init
    })
    .filter((n): n is number => n !== null)

  if (!deltas.length) return null
  return Math.round(deltas.reduce((s, n) => s + n, 0) / deltas.length)
}

/**
 * 加载「首次诊断」掌握度基线。
 * 流程：拉取诊断历史 → 取 createdAt 最早且不等于当前诊断的记录 → 取其 masteryLevels。
 * 任一环节失败或无历史，均静默保持 baselineMastery = null（不模拟）。
 */
async function loadBaselineMastery(): Promise<void> {
  try {
    const currentId = diagnosisStore.currentDiagnosis?.id
    const { list } = await diagnosisApi.getHistory({ page: 1, pageSize: 50 })
    if (!list?.length) return

    const earliest = [...list]
      .filter((d) => d.id !== currentId)
      .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime())[0]
    if (!earliest) return

    const detail = await diagnosisApi.getById(earliest.id)
    if (!detail?.masteryLevels?.length) return

    const map: Record<string, number> = {}
    detail.masteryLevels.forEach((m) => {
      map[m.knowledgePoint] = Math.round(m.mastery * 100)
    })
    baselineMastery.value = map
  } catch (e) {
    console.warn('[Dashboard] 获取首次诊断基线失败，雷达图将只展示当前掌握度', e)
    baselineMastery.value = null
  }
}

// ============================================================
//   生命周期
// ============================================================
// 统一初始化所有图表。必须在区块已可见、ref 已赋值、数据已就绪后调用，
// 否则图表会在零尺寸/隐藏状态下 init，导致「看板空白」。
function initAllCharts(): void {
  initRadarChart()
  initTrendChart()
  initCalendarChart()
}

// 安全初始化：先 reveal 区块（响应式更新需等下一帧 flush），再等浏览器布局完成
// （requestAnimationFrame）后 init + resize，彻底避免 ECharts 在 0 尺寸下初始化导致空白。
// 若布局尚未完成导致容器尺寸为 0，则轮询重试，直到具备有效尺寸或超时兜底。
function safeInitCharts(): void {
  revealAllSections()
  let tries = 0
  const MAX_TRIES = 40 // 约 2s
  const tick = () => {
    if (canInitAllCharts()) {
      initAllCharts()
      resizeAllCharts()
      return
    }
    tries += 1
    if (tries >= MAX_TRIES) {
      // 兜底：即便尺寸可能仍为 0，也尝试初始化一次，避免图表永远不渲染
      initAllCharts()
      resizeAllCharts()
      return
    }
    requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}

// 所有图表容器是否都具备有效尺寸
function canInitAllCharts(): boolean {
  const els = [chartRefs.radar.value, chartRefs.trend.value, chartRefs.calendar.value]
  return els.every((el) => !!el && el.clientWidth > 0 && el.clientHeight > 0)
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([diagnosisStore.fetchLatestDiagnosis(), pathStore.fetchCurrentPath()])
    await fetchDashboardExtras()
  } catch {
    // 仍然可以使用已有 store 数据
  } finally {
    loading.value = false
  }

  await nextTick()
  // 先让区块可见（revealAllSections 改的是响应式值，class 应用到下一帧才生效），
  // 故用 requestAnimationFrame 确保布局完成后再 init，避免 0 尺寸。
  safeInitCharts()
  setupScrollAnimation()

  // 兜底：覆盖 HMR 热替换 / ref 晚绑定 / 数据晚到达导致的图表未渲染
  window.setTimeout(() => {
    safeInitCharts()
  }, 1500)
})

onUnmounted(() => {
  disposeAllCharts()
  sectionObserver?.disconnect()
  window.removeEventListener('resize', handleWindowResize)
})

// 区块由 opacity:0 变为可见后，ECharts 实例是在「零尺寸/隐藏」状态下初始化的，
// 必须重新 resize，否则图表区域会是一片空白。
watch(
  () => ({ ...sectionVisible.value }),
  () => {
    nextTick(() => {
      resizeAllCharts()
    })
  },
  { deep: true },
)

// 数据就绪后（诊断/路径/趋势加载完成，且 loading 已结束）重新初始化图表，
// 防止 onMounted 时数据尚未到达导致图表 init 为空。
watch(
  [hasDiagnosis, () => !!pathStore.currentPath, () => cognitiveTrend.value.length, () => calendarData.value.length, () => baselineMastery.value, loading],
  () => {
    if (loading.value) return
    safeInitCharts()
  },
)

function resizeAllCharts(): void {
  Object.values(chartInstances).forEach((c) => {
    try {
      c?.resize()
    } catch {
      /* ignore */
    }
  })
}

function handleWindowResize(): void {
  resizeAllCharts()
}
window.addEventListener('resize', handleWindowResize)

// 路径数据变化时更新热力图 & 概览
watch(
  () => [pathStore.dailyTaskViews, diagnosisStore.currentDiagnosis],
  () => {
    if (!loading.value) {
      nextTick(() => {
        // 如果 API 没数据，重新生成 fallback
        if (calendarData.value.length === 0) {
          calendarData.value = buildFallbackCalendarData()
        }
        if (cognitiveTrend.value.length === 0) {
          cognitiveTrend.value = buildFallbackTrendData()
        }
        initCalendarChart()
        initTrendChart()
      })
    }
  },
  { deep: true }
)
</script>

<template>
  <div class="dashboard-page">
    <!-- ======================================== -->
    <!--  Loading State                           -->
    <!-- ======================================== -->
    <div v-if="loading" class="loading-container">
      <a-spin size="large" tip="正在加载学情数据..." />
    </div>

    <template v-else>
      <!-- ======================================== -->
      <!--  页面头部                                -->
      <!-- ======================================== -->
      <div class="page-header">
        <div class="header-left">
          <h1 class="page-title">
            <DashboardOutlined class="title-icon" />
            学情看板
          </h1>
          <span class="header-meta" v-if="hasDiagnosis">
            最近诊断 · {{ diagnosisDate }} · {{ subject }}
          </span>
        </div>
        <div class="header-right">
          <a-button @click="handleRefresh" :loading="loading">
            <template #icon><ReloadOutlined /></template>
            刷新数据
          </a-button>
        </div>
      </div>

      <!-- ======================================== -->
      <!--  看板主体（概览统计始终显示，诊断专属图表按需） -->
      <!-- ======================================== -->
      <!-- ======================================== -->
        <!--  Section 1: 进度概览卡片                  -->
        <!-- ======================================== -->
        <div
          :ref="(el) => (sectionRefs.progress.value = el as HTMLElement | null)"
          class="dashboard-section"
          :class="{ visible: sectionVisible.progress }"
        >
          <div
            v-if="!hasDiagnosis"
            class="diagnosis-notice"
          >
            <InfoCircleOutlined class="diagnosis-notice-icon" />
            <div class="diagnosis-notice-body">
              <div class="diagnosis-notice-title">尚未完成认知诊断</div>
              <div class="diagnosis-notice-desc">
                完成诊断后，下方将为你展示知识雷达、薄弱点与 AI 学习建议。当前展示基础学习概览。
              </div>
              <a-button type="primary" size="small" @click="handleGoDiagnose">
                开始诊断
              </a-button>
            </div>
          </div>
          <div class="progress-cards">
            <!-- 综合评分仪表盘 -->
            <div class="stat-card score-card">
              <div class="score-gauge">
                <svg viewBox="0 0 120 120" class="gauge-svg">
                  <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.10)" stroke-width="8" />
                  <circle
                    cx="60"
                    cy="60"
                    r="50"
                    fill="none"
                    :stroke="getScoreLevel(overallScore).color"
                    stroke-width="8"
                    stroke-linecap="round"
                    :stroke-dasharray="`${(overallScore / 100) * 314} 314`"
                    transform="rotate(-90 60 60)"
                    class="gauge-arc"
                  />
                  <text x="60" y="56" text-anchor="middle" class="gauge-value">
                    {{ overallScore }}
                  </text>
                  <text x="60" y="76" text-anchor="middle" class="gauge-unit">/ 100</text>
                </svg>
              </div>
              <div class="stat-info">
                <div class="stat-label">综合评分</div>
                <a-tag :color="getScoreLevel(overallScore).color">
                  {{ getScoreLevel(overallScore).label }}
                </a-tag>
              </div>
            </div>

            <!-- 已完成任务 -->
            <div class="stat-card">
              <div class="stat-icon-wrapper" style="background: rgba(82, 196, 26, 0.1)">
                <CheckSquareOutlined class="stat-icon" style="color: #52c41a" />
              </div>
              <div class="stat-body">
                <div class="stat-value">
                  <span class="count-up">{{ completedTaskCount }}</span>
                  <span class="stat-separator">/</span>
                  <span class="stat-total">{{ totalTasks || '—' }}</span>
                </div>
                <div class="stat-label">已完成任务</div>
                <div class="stat-sub" v-if="totalTasks > 0">
                  {{ Math.round((completedTaskCount / totalTasks) * 100) }}% 完成率
                </div>
              </div>
            </div>

            <!-- 已掌握知识点 -->
            <div class="stat-card">
              <div class="stat-icon-wrapper" style="background: rgba(79, 124, 255, 0.1)">
                <BookOutlined class="stat-icon" style="color: #4f7cff" />
              </div>
              <div class="stat-body">
                <div class="stat-value">
                  <span class="count-up">{{ masteredKPCount }}</span>
                  <span class="stat-separator">/</span>
                  <span class="stat-total">{{ totalKPCount }}</span>
                </div>
                <div class="stat-label">已掌握知识点</div>
                <div class="stat-kp-tags" v-if="masteryStats">
                  <a-tag color="success" v-if="masteryStats.excellent"
                    >优 {{ masteryStats.excellent }}</a-tag
                  >
                  <a-tag color="processing" v-if="masteryStats.proficient"
                    >良 {{ masteryStats.proficient }}</a-tag
                  >
                  <a-tag color="warning" v-if="masteryStats.developing"
                    >中 {{ masteryStats.developing }}</a-tag
                  >
                  <a-tag color="error" v-if="masteryStats.weak">弱 {{ masteryStats.weak }}</a-tag>
                </div>
              </div>
            </div>

            <!-- 学习总时长 + 连续天数 -->
            <div class="stat-card">
              <div class="stat-icon-wrapper" style="background: rgba(114, 46, 209, 0.1)">
                <ClockCircleOutlined class="stat-icon" style="color: #722ed1" />
              </div>
              <div class="stat-body">
                <div class="stat-value">
                  <span class="count-up">{{
                    overview?.totalStudyMinutes ? formatMinutes(overview.totalStudyMinutes) : '—'
                  }}</span>
                </div>
                <div class="stat-label">学习总时长</div>
                <div class="stat-sub" v-if="overview?.streakDays">
                  <FireOutlined style="color: #fa8c16; font-size: 12px" />
                  {{ overview.streakDays }} 天连续学习
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ======================================== -->
        <!--  Section 2: 知识雷达图 + 薄弱知识点       -->
        <!-- ======================================== -->
        <div
          v-if="hasDiagnosis"
          :ref="(el) => (sectionRefs.radarKp.value = el as HTMLElement | null)"
          class="dashboard-section"
          :class="{ visible: sectionVisible.radarKp }"
        >
          <div class="section-row-2col">
            <!-- 雷达图 -->
            <div class="section-card chart-card">
              <div class="card-header">
                <h3><RadarChartOutlined /> 知识掌握度雷达图</h3>
                <span class="card-hint">
                  <span class="legend-dot current"></span> 当前
                  <template v-if="baselineMastery">
                    <span class="legend-dot initial"></span> 初始
                  </template>
                </span>
              </div>
              <div class="chart-body">
                <div :ref="(el) => (chartRefs.radar.value = el as HTMLDivElement | null)" class="echarts-container"></div>
                <!-- 提升幅度：仅在存在真实首次诊断基线时展示 -->
                <div class="improvement-bar" v-if="masteryLevels.length && avgImprovement !== null">
                  <RiseOutlined :style="{ color: avgImprovement >= 0 ? '#52c41a' : '#ff4d4f' }" />
                  <span>
                    较首次诊断平均{{ avgImprovement >= 0 ? '提升' : '下降' }}
                    <b>{{ Math.abs(avgImprovement) }}%</b>
                  </span>
                </div>
                <div class="improvement-bar" v-else-if="masteryLevels.length">
                  <InfoCircleOutlined style="color: #94a3b8" />
                  <span>暂无历史诊断可对比，完成第二次诊断后可查看进步幅度</span>
                </div>
              </div>
            </div>

            <!-- 薄弱知识点 -->
            <div class="section-card weak-points-card">
              <div class="card-header">
                <h3><WarningOutlined /> 薄弱知识点</h3>
                <a-tag color="error" v-if="lowMasteryKPs.length"
                  >{{ lowMasteryKPs.length }} 个待提升</a-tag
                >
                <a-tag color="success" v-else>全部达标</a-tag>
              </div>
              <div class="weak-points-list">
                <template v-if="lowMasteryKPs.length > 0">
                  <div
                    v-for="kp in lowMasteryKPs.slice(0, 8)"
                    :key="kp.knowledgePoint"
                    class="weak-point-item"
                  >
                    <div class="wp-header">
                      <span class="wp-name">{{ kp.knowledgePoint }}</span>
                      <a-tag :color="kp.level === 'weak' ? 'error' : 'warning'" size="small">
                        {{ Math.round(kp.mastery * 100) }}%
                      </a-tag>
                    </div>
                    <div class="wp-bar-bg">
                      <div
                        class="wp-bar-fill"
                        :class="kp.level"
                        :style="{ width: `${Math.round(kp.mastery * 100)}%` }"
                      ></div>
                    </div>
                    <div class="wp-meta" v-if="kp.confidence">
                      <span>置信度 {{ Math.round(kp.confidence * 100) }}%</span>
                    </div>
                  </div>
                </template>
                <div v-else class="weak-empty">
                  <TrophyOutlined style="font-size: 36px; color: #52c41a" />
                  <p>所有知识点掌握度达标！继续保持</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ======================================== -->
        <!--  Section 3: 认知负荷趋势                  -->
        <!-- ======================================== -->
        <div
          v-if="hasDiagnosis"
          :ref="(el) => (sectionRefs.trend.value = el as HTMLElement | null)"
          class="dashboard-section"
          :class="{ visible: sectionVisible.trend }"
        >
          <div class="section-card">
            <div class="card-header">
              <h3><LineChartOutlined /> 认知负荷趋势</h3>
              <span class="card-hint">
                越低越好 · 虚线为负荷警戒线
                <template v-if="cognitiveTrend.length > 10">
                  · 默认展示最近 10 次，可拖动下方滑块查看更早记录
                </template>
              </span>
            </div>
            <div class="chart-body">
              <div :ref="(el) => (chartRefs.trend.value = el as HTMLDivElement | null)" class="echarts-container" style="height: 340px"></div>
            </div>
            <!-- 当前认知负荷三维度 -->
            <div class="cl-dimensions">
              <div class="cl-dim-item">
                <div class="cl-dim-label">记忆负荷</div>
                <a-progress
                  :percent="Math.round(cognitiveLoad.memoryLoad * 100)"
                  :stroke-color="cognitiveLoad.memoryLoad > 0.6 ? '#FF4D4F' : '#FA8C16'"
                  size="small"
                />
              </div>
              <div class="cl-dim-item">
                <div class="cl-dim-label">注意力负荷</div>
                <a-progress
                  :percent="Math.round(cognitiveLoad.attentionLoad * 100)"
                  :stroke-color="cognitiveLoad.attentionLoad > 0.6 ? '#FF4D4F' : '#722ED1'"
                  size="small"
                />
              </div>
              <div class="cl-dim-item">
                <div class="cl-dim-label">加工负荷</div>
                <a-progress
                  :percent="Math.round(cognitiveLoad.processingLoad * 100)"
                  :stroke-color="cognitiveLoad.processingLoad > 0.6 ? '#FF4D4F' : '#52C41A'"
                  size="small"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- ======================================== -->
        <!--  Section 4: 薄弱点详情 + AI 学习建议      -->
        <!-- ======================================== -->
        <div
          v-if="hasDiagnosis"
          :ref="(el) => (sectionRefs.weakpointSuggestion.value = el as HTMLElement | null)"
          class="dashboard-section"
          :class="{ visible: sectionVisible.weakpointSuggestion }"
        >
          <div class="section-row-2col wp-sg-layout">
            <!-- 薄弱点详细列表 -->
            <div class="section-card wp-sg-card">
              <div class="card-header">
                <h3><AimOutlined /> 薄弱点详情</h3>
                <span class="card-hint" v-if="weakPoints.length"
                  >{{ weakPoints.length }} 个诊断薄弱点</span
                >
              </div>
              <div class="weak-points-detailed">
                <a-table
                  v-if="weakPoints.length > 0"
                  class="weak-point-table"
                  size="small"
                  row-key="knowledgePoint"
                  :columns="weakPointColumns"
                  :data-source="weakPointRows"
                  :pagination="
                    weakPointRows.length > 5 ? { pageSize: 5, size: 'small' } : false
                  "
                  :scroll="{ x: 'max-content' }"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'severity'">
                      <a-tag :color="getSeverityColor(record.severity)">
                        {{ getSeverityLabel(record.severity) }}
                      </a-tag>
                    </template>
                    <template v-else-if="column.key === 'reason'">
                      <a-tooltip :title="record.reason">
                        <span class="wp-cell-ellipsis">{{ record.reason || '—' }}</span>
                      </a-tooltip>
                    </template>
                    <template v-else-if="column.key === 'remediation'">
                      <a-tooltip :title="record.suggestedRemediation">
                        <span class="wp-cell-ellipsis">
                          {{ record.suggestedRemediation || '—' }}
                        </span>
                      </a-tooltip>
                    </template>
                    <template v-else-if="column.key === 'action'">
                      <a-button type="link" size="small" @click="openWeakPointDetail(record)">
                        查看详情
                      </a-button>
                    </template>
                  </template>
                </a-table>
                <div v-else class="weak-empty">
                  <TrophyOutlined style="font-size: 36px; color: #52c41a" />
                  <p>未检测到薄弱点，学习状态良好！</p>
                </div>
              </div>
            </div>

            <!-- AI 学习建议 -->
            <div class="section-card wp-sg-card">
              <div class="card-header">
                <h3><BulbOutlined /> AI 学习建议</h3>
                <span class="card-hint">基于星火大模型分析</span>
              </div>
              <div class="suggestions-list">
                <div
                  v-if="!suggestions.length"
                  class="weak-empty"
                >
                  <BulbOutlined style="font-size: 24px; margin-bottom: 8px; opacity: 0.5" />
                  <span>暂无 AI 学习建议</span>
                </div>
                <div
                  v-for="(sg, idx) in suggestions"
                  :key="idx"
                  class="suggestion-item"
                  :style="{
                    background: getSuggestionBgColor(sg.category),
                    borderColor: getSuggestionBorderColor(sg.category)
                  }"
                >
                  <div class="sg-header">
                    <component :is="getSuggestionIcon(sg.category)" class="sg-icon" />
                    <span class="sg-title">{{ sg.title }}</span>
                    <a-tag
                      v-if="sg.priority <= 2"
                      :color="sg.priority === 1 ? 'error' : 'warning'"
                      size="small"
                    >
                      优先
                    </a-tag>
                  </div>
                  <p class="sg-content">{{ sg.content }}</p>
                  <div class="sg-related" v-if="sg.relatedKPs?.length">
                    <a-tag
                      v-for="kp in sg.relatedKPs"
                      :key="kp"
                      size="small"
                      style="margin-right: 4px"
                    >
                      {{ kp }}
                    </a-tag>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ======================================== -->
        <!--  Section 5: 学习日历热力图                -->
        <!-- ======================================== -->
        <div
          :ref="(el) => (sectionRefs.calendar.value = el as HTMLElement | null)"
          class="dashboard-section"
          :class="{ visible: sectionVisible.calendar }"
        >
          <div class="section-card">
            <div class="card-header">
              <h3><CalendarOutlined /> 学习日历</h3>
              <div class="calendar-nav">
                <a-button size="small" type="text" @click="shiftCalendarMonth(-1)"><CaretLeftOutlined /></a-button>
                <span class="calendar-label">{{ calendarYear }} 年 {{ calendarMonth }} 月</span>
                <a-button size="small" type="text" @click="shiftCalendarMonth(1)"><CaretRightOutlined /></a-button>
              </div>
            </div>
            <div class="chart-body">
              <div :ref="(el) => (chartRefs.calendar.value = el as HTMLDivElement | null)" class="echarts-container" style="height: 220px"></div>
            </div>
          </div>
        </div>
    </template>

    <!-- 薄弱点详情抽屉 -->
    <a-drawer
      v-model:open="weakPointDetailVisible"
      title="薄弱点详情"
      placement="right"
      :width="420"
    >
      <template v-if="activeWeakPoint">
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item label="知识点">
            {{ activeWeakPoint.knowledgePoint }}
          </a-descriptions-item>
          <a-descriptions-item label="严重程度">
            <a-tag :color="getSeverityColor(activeWeakPoint.severity)">
              {{ getSeverityLabel(activeWeakPoint.severity) }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="薄弱原因">
            {{ activeWeakPoint.reason || '暂无说明' }}
          </a-descriptions-item>
          <a-descriptions-item label="改进建议">
            {{ activeWeakPoint.suggestedRemediation || '暂无建议' }}
          </a-descriptions-item>
        </a-descriptions>
      </template>
    </a-drawer>
  </div>
</template>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

// ============================================================
//   Variables
// ============================================================
@card-padding: clamp(0.875rem, 1.25rem + 0.3vw, 1.5rem);
@section-gap: clamp(0.625rem, 1.25rem + 0.3vw, 1.5rem);

// ============================================================
//   Page Layout
// ============================================================
.dashboard-page {
  max-width: var(--content-max-width, clamp(60rem, 80rem, 80rem));
  margin: 0 auto;
  padding: @spacing-lg @spacing-md @spacing-2xl;
}

.loading-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
}

// ============================================================
//   Page Header
// ============================================================
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: @spacing-lg;
  flex-wrap: wrap;
  gap: 12px;

  .header-left {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
  }

  .page-title {
    font-size: @font-size-2xl;
    font-weight: @font-weight-bold;
    color: @gray-50;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 10px;

    .title-icon {
      color: @brand-oat-300;
      font-size: 24px;
    }
  }

  .header-meta {
    font-size: @font-size-sm;
    color: @gray-300;
  }

  .header-right {
    display: flex;
    gap: @spacing-sm;
  }
}

// ============================================================
//   Empty State
// ============================================================
.empty-state {
  display: flex;
  justify-content: center;
  padding: 80px 0;
}

.empty-card {
  text-align: center;
  max-width: 400px;

  .empty-icon {
    font-size: 72px;
    color: rgba(212, 163, 115, 0.35);
    margin-bottom: 20px;
  }

  h2 {
    font-size: @font-size-xl;
    color: @brand-oat-300;
    margin: 0 0 8px;
  }

  p {
    color: rgba(212, 163, 115, 0.6);
    margin: 0 0 24px;
    font-size: @font-size-base;
  }
}

// ============================================================
//   Diagnosis Notice — 纯手写 div，不依赖 Ant Design Alert 样式
// ============================================================
.diagnosis-notice {
  display: flex;
  gap: 16px;
  padding: 20px 24px;
  background: rgba(30, 41, 59, 0.92);
  border: 1px solid rgba(74, 108, 247, 0.4);
  border-left: 4px solid #4a6cf7;
  border-radius: 12px;
  margin-bottom: 24px;
}

.diagnosis-notice-icon {
  font-size: 24px;
  color: #4a6cf7;
  flex-shrink: 0;
  margin-top: 2px;
}

.diagnosis-notice-body {
  flex: 1;
  min-width: 0;
}

.diagnosis-notice-title {
  font-size: 15px;
  font-weight: 700;
  color: #f1f5f9;
  margin-bottom: 6px;
}

.diagnosis-notice-desc {
  font-size: 13px;
  color: #cbd5e1;
  line-height: 1.65;
  margin-bottom: 12px;
}

// ============================================================
//   Section Animation
// ============================================================
.dashboard-section {
  opacity: 0;
  transform: translateY(30px);
  transition:
    opacity 0.6s ease,
    transform 0.6s ease;
  margin-bottom: @section-gap;

  &.visible {
    opacity: 1;
    transform: translateY(0);
  }
}

// ============================================================
//   Progress Cards Grid
// ============================================================
.progress-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  .glass-card();
  padding: @card-padding;
  display: flex;
  align-items: center;
  gap: 16px;
  .glass-card-hover();

  &.score-card {
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 8px;
  }
}

.stat-icon-wrapper {
  width: 48px;
  height: 48px;
  border-radius: @radius-md;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  .stat-icon {
    font-size: 22px;
  }
}

.stat-body {
  min-width: 0;
}

.stat-value {
  font-size: @font-size-xl;
  font-weight: @font-weight-bold;
  color: @gray-50;
  line-height: 1.2;

  .count-up {
    font-size: @font-size-2xl;
  }

  .stat-separator {
    color: @gray-300;
    font-weight: @font-weight-normal;
    margin: 0 2px;
  }

  .stat-total {
    color: @gray-300;
    font-weight: @font-weight-medium;
  }
}

.stat-label {
  font-size: @font-size-sm;
  color: @gray-300;
  margin-top: 2px;
}

.stat-sub {
  font-size: @font-size-xs;
  color: @gray-300;
  margin-top: 4px;
}

.stat-kp-tags {
  margin-top: 6px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

// ============================================================
//   Score Gauge (SVG)
// ============================================================
.score-gauge {
  .gauge-svg {
    width: 100px;
    height: 100px;
  }

  .gauge-arc {
    transition: stroke-dasharray 1.5s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .gauge-value {
    font-size: 24px;
    font-weight: @font-weight-bold;
    fill: @gray-50;
    dominant-baseline: middle;
  }

  .gauge-unit {
    font-size: 12px;
    fill: @gray-300;
    dominant-baseline: middle;
  }
}

.stat-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

// ============================================================
//   Section Card (generic)
// ============================================================
.section-card {
  .glass-card();
  overflow: hidden;

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px @card-padding;
    border-bottom: 1px solid @glass-border;

    h3 {
      margin: 0;
      font-size: @font-size-md;
      font-weight: @font-weight-semibold;
      color: @gray-50;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .card-hint {
      font-size: @font-size-xs;
      color: @gray-300;
    }
  }

  .chart-body {
    padding: @card-padding;
    position: relative;
  }
}

// ============================================================
//   ECharts Container (响应式宽高比)
// ============================================================
.echarts-container {
  width: 100%;
  aspect-ratio: 16 / 10;
  min-height: 240px;
}

// ============================================================
//   Two-Column Row
// ============================================================
.section-row-2col {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 16px;
  align-items: start;
}

// Section 4: 薄弱点详情 + AI 学习建议 —— 等高协调布局
.wp-sg-layout {
  grid-template-columns: 1.1fr 1fr;
  align-items: stretch;
  max-height: 460px;
}

.wp-sg-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  margin: 0;

  // 卡片内部内容区填充并独立滚动，使两卡底部齐平
  .weak-points-detailed {
    flex: 1;
    min-height: 0;
    overflow: auto;
  }

  .suggestions-list {
    flex: 1;
    min-height: 0;
    max-height: none;
  }

  // 无数据时垂直居中，避免贴顶与右卡失衡
  .weak-empty {
    display: flex;
    flex-direction: column;
    justify-content: center;
    min-height: 100%;
    margin: 0;
    padding: 24px @card-padding;
  }

  // 统一两卡内部滚动条风格
  .weak-points-detailed,
  .suggestions-list {
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 255, 255, 0.18) transparent;

    &::-webkit-scrollbar {
      width: 6px;
    }

    &::-webkit-scrollbar-thumb {
      background: rgba(255, 255, 255, 0.18);
      border-radius: 3px;
    }

    &::-webkit-scrollbar-track {
      background: transparent;
    }
  }
}

// ============================================================
//   Radar Chart extras
// ============================================================
.improvement-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 0;
  font-size: @font-size-sm;
  color: @gray-200;

  b {
    color: @color-success;
    font-size: @font-size-md;
  }
}

.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin: 0 4px 0 12px;

  &.current {
    background: @brand-blue-500;
    box-shadow: 0 0 4px rgba(79, 124, 255, 0.4);
  }
  &.initial {
    background: @brand-oat-400;
  }
}

// ============================================================
//   Weak Points List
// ============================================================
.weak-points-card {
  min-height: 320px;
}

.weak-points-list {
  padding: 12px @card-padding;
  max-height: 360px;
  overflow-y: auto;
}

.weak-point-item {
  padding: 10px 0;
  border-bottom: 1px solid @glass-border;

  &:last-child {
    border-bottom: none;
  }

  .wp-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }

  .wp-name {
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
    color: @gray-100;
  }

  .wp-bar-bg {
    height: 6px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 3px;
    overflow: hidden;
  }

  .wp-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 1.2s cubic-bezier(0.4, 0, 0.2, 1);
    background: @brand-blue-500;

    &.weak {
      background: linear-gradient(90deg, #ff4d4f, #fa8c16);
    }
    &.developing {
      background: linear-gradient(90deg, #fa8c16, @brand-blue-500);
    }
  }

  .wp-meta {
    font-size: @font-size-xs;
    color: @gray-300;
    margin-top: 4px;
  }
}

.weak-empty {
  text-align: center;
  padding: 40px 0;
  color: @gray-300;
  font-size: @font-size-sm;
}

// ============================================================
//   Cognitive Load Dimensions
// ============================================================
.cl-dimensions {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  padding: 12px @card-padding @card-padding;
  border-top: 1px solid @glass-border;
}

.cl-dim-item {
  .cl-dim-label {
    font-size: @font-size-xs;
    color: @gray-300;
    margin-bottom: 4px;
  }
}

// ============================================================
//   Weak Points Detailed
// ============================================================
.weak-points-detailed {
  padding: 12px @card-padding;
}

// 薄弱点表格（深色主题适配）
.weak-point-table {
  :deep(.ant-table) {
    background: transparent;
    font-size: @font-size-sm;
  }

  :deep(.ant-table-thead > tr > th) {
    background: rgba(255, 255, 255, 0.05);
    color: @gray-200;
    border-bottom-color: rgba(255, 255, 255, 0.1);
    font-weight: 600;

    &::before {
      display: none !important;
    }
  }

  :deep(.ant-table-tbody > tr > td) {
    background: transparent;
    color: @gray-200;
    border-bottom-color: rgba(255, 255, 255, 0.06);
  }

  :deep(.ant-table-tbody > tr:hover > td) {
    background: rgba(255, 255, 255, 0.05) !important;
  }

  :deep(.ant-table-cell-fix-right) {
    background: @gray-800 !important;
  }

  :deep(.ant-table-column-sort) {
    background: rgba(255, 255, 255, 0.03);
  }

  :deep(.ant-table-column-sorter),
  :deep(.ant-table-filter-trigger) {
    color: @gray-400;
  }

  :deep(.ant-pagination) {
    color: @gray-300;

    .ant-pagination-item a {
      color: @gray-300;
    }

    .ant-pagination-item-active {
      background: transparent;
      border-color: @brand-blue-500;

      a {
        color: @brand-blue-400;
      }
    }

    .ant-pagination-prev button,
    .ant-pagination-next button {
      color: @gray-300;
    }
  }

  .wp-cell-ellipsis {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

// ============================================================
//   AI Suggestions
// ============================================================
.suggestions-list {
  padding: 12px @card-padding;
  max-height: 420px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.suggestion-item {
  padding: 12px 14px;
  border: 1px solid;
  border-radius: @radius-sm;
  transition: box-shadow @transition-fast;

  &:hover {
    box-shadow: @shadow-sm;
  }

  .sg-header {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 6px;
  }

  .sg-icon {
    font-size: 16px;
    line-height: 1;
    flex-shrink: 0;
    color: @brand-cyan-400;
  }

  .sg-title {
    font-size: @font-size-sm;
    font-weight: @font-weight-semibold;
    color: @gray-50;
    flex: 1;
  }

  .sg-content {
    font-size: @font-size-sm;
    color: @gray-200;
    margin: 0;
    line-height: 1.6;
  }

  .sg-related {
    margin-top: 8px;
  }
}

// ============================================================
//   Calendar Navigation
// ============================================================
.calendar-nav {
  display: flex;
  align-items: center;
  gap: 8px;

  .calendar-label {
    font-size: @font-size-sm;
    color: @gray-200;
    font-weight: @font-weight-medium;
    min-width: 80px;
    text-align: center;
  }
}

// ============================================================
//   Responsive
// ============================================================
@media (max-width: @screen-lg) {
  .dashboard-page {
    max-width: 100%;
  }
}

@media (max-width: @screen-md) {
  .progress-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .section-row-2col {
    grid-template-columns: 1fr;
  }

  .cl-dimensions {
    grid-template-columns: 1fr;
  }

  .echarts-container {
    aspect-ratio: 4 / 3;
    min-height: 260px;
  }
}

@media (max-width: @screen-sm) {
  .page-header {
    flex-direction: column;

    .header-right {
      width: 100%;
    }
  }

  .progress-cards {
    grid-template-columns: 1fr;
  }

  .stat-card {
    padding: 0.875rem;
  }

  .dashboard-page {
    padding: @spacing-md @spacing-sm @spacing-xl;
  }

  .echarts-container {
    aspect-ratio: 4 / 3;
    min-height: 240px;
  }
}

@media (max-width: @screen-xs) {
  .dashboard-page {
    padding: @spacing-sm @spacing-xs @spacing-md;
  }

  .progress-cards {
    gap: 0.5rem;
  }

  .stat-card {
    padding: 0.625rem 0.75rem;
  }

  .echarts-container {
    aspect-ratio: 1 / 1;
    min-height: 220px;
  }

  .section-row-2col {
    gap: 0.5rem;
  }
}
</style>
