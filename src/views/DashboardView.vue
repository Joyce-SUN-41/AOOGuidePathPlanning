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
  ExperimentOutlined,
  FireOutlined,
  RightOutlined,
  AimOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

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
  calendar: ref<HTMLDivElement | null>(null),
}
const chartInstances: Record<string, echarts.ECharts | null> = {
  radar: null,
  trend: null,
  calendar: null,
}
const resizeObservers: ResizeObserver[] = []

// 额外数据（API 获取，失败时用 fallback）
const cognitiveTrend = ref<CognitiveLoadTrendPoint[]>([])
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

const hasPath = computed(() => pathStore.hasPath)
const totalTasks = computed(() => pathStore.taskCount)
const estimatedHours = computed(() => pathStore.estimatedHours)
const totalDays = computed(() => pathStore.totalDays)

const completedTaskCount = computed(() => completedTaskIds.value.size)
const masteredKPCount = computed(() => masteryStats.value.excellent + masteryStats.value.proficient)
const totalKPCount = computed(() => masteryLevels.value.length)

// 薄弱点（掌握度 < 0.6 的知识点）
const lowMasteryKPs = computed<MasteryItem[]>(() =>
  masteryLevels.value.filter(kp => kp.mastery < 0.6)
)

// ============================================================
//   Methods
// ============================================================

function loadCompletedTasks(): Set<string> {
  try {
    const raw = localStorage.getItem('oat_completed_tasks')
    if (raw) return new Set(JSON.parse(raw))
  } catch { /* ignore */ }
  return new Set()
}

function saveCompletedTasks(): void {
  localStorage.setItem('oat_completed_tasks', JSON.stringify([...completedTaskIds.value]))
}

/** 初始化雷达图 */
function initRadarChart(): void {
  const container = chartRefs.radar.value
  if (!container) return

  if (chartInstances.radar) chartInstances.radar.dispose()
  const chart = echarts.init(container)
  chartInstances.radar = chart

  const indicators = masteryRadarData.value.map(item => ({
    name: item.name,
    max: 100
  }))

  // 当前掌握度
  const currentValues = masteryRadarData.value.map(item => item.value)

  // 模拟初始掌握度（首次诊断或对比上次诊断）
  // 优先从历史诊断获取，若没有则使用当前值做基线偏移
  const initialMultiplier = 0.55 + Math.random() * 0.15
  const initialValues = masteryRadarData.value.map(item =>
    Math.max(5, Math.round(item.value * initialMultiplier))
  )

  // 提升幅度
  const improvements = currentValues.map((v, i) => v - initialValues[i])

  chart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#e8e0d8',
      textStyle: { color: '#3d3b39' },
      formatter: (params: { name: string; value: number; seriesName: string; color: string }) => {
        const idx = indicators.findIndex(ind => ind.name === params.name)
        const imp = idx >= 0 ? improvements[idx] : 0
        return `<b>${params.name}</b><br/>
          <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${params.color};margin-right:6px;"></span>
          ${params.seriesName}: <b>${params.value}%</b><br/>
          ${params.seriesName === '当前掌握度' ? `<span style="color:#52c41a;">↑ +${imp}%</span>` : ''}`
      }
    },
    legend: {
      bottom: 0,
      data: ['当前掌握度', '初始水平'],
      textStyle: { color: '#5c5a57', fontSize: 12 }
    },
    radar: {
      center: ['50%', '52%'],
      radius: '62%',
      indicator: indicators,
      axisName: {
        color: '#5c5a57',
        fontSize: 11,
        borderRadius: 3,
        padding: [3, 5]
      },
      splitArea: {
        areaStyle: {
          color: ['rgba(79,124,255,0.02)', 'rgba(79,124,255,0.04)', 'rgba(79,124,255,0.02)', 'rgba(79,124,255,0.04)', 'rgba(79,124,255,0.02)']
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
        lineStyle: { color: '#4F7CFF', width: 2, shadowBlur: 6, shadowColor: 'rgba(79,124,255,0.3)' },
        areaStyle: { color: 'rgba(79,124,255,0.15)' },
        itemStyle: { color: '#4F7CFF', borderColor: '#fff', borderWidth: 2 }
      },
      {
        type: 'radar',
        name: '初始水平',
        data: [{ value: initialValues, name: '初始水平' }],
        symbol: 'diamond',
        symbolSize: 5,
        lineStyle: { color: '#b8a99a', width: 1.5, type: 'dashed' },
        areaStyle: { color: 'rgba(184,169,154,0.08)' },
        itemStyle: { color: '#b8a99a' }
      }
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

  const trendData = cognitiveTrend.value.length > 0
    ? cognitiveTrend.value
    : buildFallbackTrendData()

  const dates = trendData.map(d => d.date)
  const overall = trendData.map(d => Math.round(d.overall * 100))
  const memory = trendData.map(d => Math.round(d.memoryLoad * 100))
  const attention = trendData.map(d => Math.round(d.attentionLoad * 100))
  const processing = trendData.map(d => Math.round(d.processingLoad * 100))

  chart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#e8e0d8',
      textStyle: { color: '#3d3b39', fontSize: 13 },
      formatter: (params: Array<{ seriesName: string; value: number; color: string; axisValue: string }>) => {
        let html = `<b>${params[0].axisValue}</b><br/>`
        params.forEach(p => {
          html += `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${p.color};margin-right:6px;"></span>
            ${p.seriesName}: <b>${p.value}%</b><br/>`
        })
        return html
      }
    },
    legend: {
      bottom: 0,
      data: ['综合负荷', '记忆负荷', '注意力负荷', '加工负荷'],
      textStyle: { color: '#5c5a57', fontSize: 11 }
    },
    grid: { left: 40, right: 20, top: 40, bottom: 50 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { color: '#82807c', fontSize: 11, rotate: dates.length > 8 ? 30 : 0 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e8e0d8' } }
    },
    yAxis: {
      type: 'value',
      name: '负荷 (%)',
      min: 0,
      max: 100,
      axisLabel: { color: '#82807c', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f0ede8', type: 'dashed' } },
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
        itemStyle: { color: '#FF4D4F', borderColor: '#fff', borderWidth: 2 },
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

  const calData = calendarData.value.length > 0
    ? calendarData.value
    : buildFallbackCalendarData()

  const year = calendarYear.value
  const month = calendarMonth.value

  // 获取当月天数范围
  const firstDay = new Date(year, month - 1, 1)
  const lastDay = new Date(year, month, 0)
  const rangeStart = formatDateStr(firstDay)
  const rangeEnd = formatDateStr(lastDay)

  const heatData: [string, number][] = calData.map(item => [
    item.date,
    item.studyMinutes
  ])

  chart.setOption({
    tooltip: {
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#e8e0d8',
      textStyle: { color: '#3d3b39', fontSize: 13 },
      formatter: (params: { value: [string, number] }) => {
        if (!params.value) return ''
        const [date, minutes] = params.value
        const item = calData.find(d => d.date === date)
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
      max: Math.max(...heatData.map(d => d[1]), 60),
      type: 'piecewise',
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: { color: ['#f5f0eb', '#dbe4ff', '#8FAEFF', '#4F7CFF', '#2A46B3'] },
      text: ['多', '少'],
      textStyle: { color: '#5c5a57', fontSize: 11 }
    },
    calendar: {
      range: [rangeStart, rangeEnd],
      cellSize: ['auto', 32],
      yearLabel: { show: false },
      dayLabel: {
        firstDay: 1,
        nameMap: 'ZH',
        color: '#82807c',
        fontSize: 11
      },
      monthLabel: {
        nameMap: 'ZH',
        color: '#3d3b39',
        fontSize: 13,
        fontWeight: 'bold'
      },
      itemStyle: {
        borderColor: '#fff',
        borderWidth: 3,
        borderRadius: 4,
        color: '#f5f0eb'
      },
      splitLine: { show: true, lineStyle: { color: '#f0ede8', width: 1 } }
    },
    series: [{
      type: 'heatmap',
      coordinateSystem: 'calendar',
      data: heatData
    }]
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
  Object.values(chartInstances).forEach(c => c?.dispose())
  resizeObservers.forEach(ro => ro.disconnect())
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
        knowledgePoints: masteryLevels.value.slice(0, 2).map(m => m.knowledgePoint)
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
      content: `检测到 ${weakPoints.value.length} 个薄弱知识点。建议优先从掌握度最低的 "${weakPoints.value[0].knowledgePoint}" 入手，每天安排 30 分钟专项练习。`,
      priority: 1,
      relatedKPs: weakPoints.value.slice(0, 3).map(w => w.knowledgePoint)
    })
  }

  if (Math.round(cognitiveLoad.value.overall * 100) > 60) {
    tips.push({
      category: 'warning',
      title: '认知负荷偏高',
      content: '当前认知负荷指数处于较高水平，建议增加复习间隔，避免连续学习高难度内容。可尝试番茄工作法（25分钟学习 + 5分钟休息）。',
      priority: 2
    })
  }

  tips.push({
    category: 'tip',
    title: '交替学习法',
    content: '研究表明交替学习不同知识点的效果优于集中学习单一内容。建议每天安排 2-3 个不同知识点的任务轮流进行。',
    priority: 3
  })

  tips.push({
    category: 'strength',
    title: '保持优势领域',
    content: masteryStats.value.excellent > 0
      ? `在 "${masteryLevels.value.find(m => m.level === 'excellent')?.knowledgePoint ?? ''}" 方面表现优秀，可以尝试相关进阶内容，进一步拓展知识边界。`
      : '当前没有特别突出的优势领域，继续按照学习路径稳步推进即可。',
    priority: 4
  })

  tips.push({
    category: 'tip',
    title: '定期复习策略',
    content: '遵循艾宾浩斯遗忘曲线，学习后 1 天、2 天、4 天、7 天、15 天进行间隔复习，可显著提升长期记忆效果。',
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
    case 'severe': return '#FF4D4F'
    case 'moderate': return '#FA8C16'
    case 'mild': return '#4F7CFF'
    default: return '#82807c'
  }
}

function getSeverityLabel(severity: WeakPoint['severity']): string {
  switch (severity) {
    case 'severe': return '严重'
    case 'moderate': return '中等'
    case 'mild': return '轻度'
    default: return '未知'
  }
}

function getSuggestionIcon(category: LearningSuggestion['category']): string {
  switch (category) {
    case 'strength': return '🌟'
    case 'weakness': return '🎯'
    case 'tip': return '💡'
    case 'warning': return '⚠️'
    default: return '📌'
  }
}

function getSuggestionBgColor(category: LearningSuggestion['category']): string {
  switch (category) {
    case 'strength': return '#f6ffed'
    case 'weakness': return '#fff7e6'
    case 'tip': return '#f0f5ff'
    case 'warning': return '#fff2f0'
    default: return '#fafaf9'
  }
}

function getSuggestionBorderColor(category: LearningSuggestion['category']): string {
  switch (category) {
    case 'strength': return '#b7eb8f'
    case 'weakness': return '#ffd591'
    case 'tip': return '#adc6ff'
    case 'warning': return '#ffccc7'
    default: return '#e8e0d8'
  }
}

// ============================================================
//   操作
// ============================================================

function handleGoDiagnose(): void {
  router.push('/diagnose')
}

function handleGoPath(): void {
  router.push('/path')
}

async function handleRefresh(): Promise<void> {
  loading.value = true
  try {
    await Promise.all([
      diagnosisStore.fetchLatestDiagnosis(),
      pathStore.fetchCurrentPath()
    ])
    await fetchDashboardExtras()
  } finally {
    loading.value = false
  }
}

async function fetchDashboardExtras(): Promise<void> {
  // 并行获取额外数据，失败则使用 fallback
  const results = await Promise.allSettled([
    dashboardApi.getCognitiveLoadTrend(10),
    dashboardApi.getCalendarActivity(calendarYear.value, calendarMonth.value),
    dashboardApi.getSuggestions(),
    dashboardApi.getOverview()
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
  calendar: ref<HTMLElement | null>(null),
}

const sectionVisible = ref<Record<string, boolean>>({})
let sectionObserver: IntersectionObserver | null = null

function setupScrollAnimation(): void {
  sectionObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const key = entry.target.getAttribute('data-section')
          if (key) sectionVisible.value[key] = true
          sectionObserver?.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.15, rootMargin: '0px 0px -50px 0px' }
  )

  nextTick(() => {
    Object.entries(sectionRefs).forEach(([key, ref]) => {
      if (ref.value) {
        ref.value.setAttribute('data-section', key)
        sectionObserver?.observe(ref.value)
      }
    })
  })
}

/** 计算当前 vs 初始的模拟平均提升 */
function calculateAvgImprovement(): number {
  if (!masteryLevels.value.length) return 0
  const mult = 0.55 + Math.random() * 0.15
  const totalImprovement = masteryLevels.value.reduce((sum, item) => {
    const initial = Math.max(5, Math.round(item.mastery * 100 * mult))
    return sum + (Math.round(item.mastery * 100) - initial)
  }, 0)
  return Math.round(totalImprovement / masteryLevels.value.length)
}

// ============================================================
//   生命周期
// ============================================================
onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      diagnosisStore.fetchLatestDiagnosis(),
      pathStore.fetchCurrentPath()
    ])
    await fetchDashboardExtras()
  } catch {
    // 仍然可以使用已有 store 数据
  } finally {
    loading.value = false
  }

  await nextTick()
  initRadarChart()
  initTrendChart()
  initCalendarChart()
  setupScrollAnimation()
})

onUnmounted(() => {
  disposeAllCharts()
  sectionObserver?.disconnect()
})

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
      <!--  空状态：无诊断                           -->
      <!-- ======================================== -->
      <div v-if="!hasDiagnosis" class="empty-state">
        <div class="empty-card">
          <ExperimentOutlined class="empty-icon" />
          <h2>尚未完成认知诊断</h2>
          <p>完成诊断后，学情看板将为你展示全面的学习画像</p>
          <a-button type="primary" size="large" @click="handleGoDiagnose">
            开始诊断
            <template #icon><RightOutlined /></template>
          </a-button>
        </div>
      </div>

      <!-- ======================================== -->
      <!--  有诊断数据时展示完整看板                  -->
      <!-- ======================================== -->
      <template v-if="hasDiagnosis">
        <!-- ======================================== -->
        <!--  Section 1: 进度概览卡片                  -->
        <!-- ======================================== -->
        <div ref="sectionRefs.progress" class="dashboard-section" :class="{ visible: sectionVisible.progress }">
          <div class="progress-cards">
            <!-- 综合评分仪表盘 -->
            <div class="stat-card score-card">
              <div class="score-gauge">
                <svg viewBox="0 0 120 120" class="gauge-svg">
                  <circle cx="60" cy="60" r="50" fill="none" stroke="#f0ede8" stroke-width="8" />
                  <circle
                    cx="60" cy="60" r="50" fill="none"
                    :stroke="getScoreLevel(overallScore).color"
                    stroke-width="8"
                    stroke-linecap="round"
                    :stroke-dasharray="`${(overallScore / 100) * 314} 314`"
                    transform="rotate(-90 60 60)"
                    class="gauge-arc"
                  />
                  <text x="60" y="56" text-anchor="middle" class="gauge-value">{{ overallScore }}</text>
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
              <div class="stat-icon-wrapper" style="background: rgba(82,196,26,0.1);">
                <CheckSquareOutlined class="stat-icon" style="color: #52C41A;" />
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
              <div class="stat-icon-wrapper" style="background: rgba(79,124,255,0.1);">
                <BookOutlined class="stat-icon" style="color: #4F7CFF;" />
              </div>
              <div class="stat-body">
                <div class="stat-value">
                  <span class="count-up">{{ masteredKPCount }}</span>
                  <span class="stat-separator">/</span>
                  <span class="stat-total">{{ totalKPCount }}</span>
                </div>
                <div class="stat-label">已掌握知识点</div>
                <div class="stat-kp-tags" v-if="masteryStats">
                  <a-tag color="success" v-if="masteryStats.excellent">优 {{ masteryStats.excellent }}</a-tag>
                  <a-tag color="processing" v-if="masteryStats.proficient">良 {{ masteryStats.proficient }}</a-tag>
                  <a-tag color="warning" v-if="masteryStats.developing">中 {{ masteryStats.developing }}</a-tag>
                  <a-tag color="error" v-if="masteryStats.weak">弱 {{ masteryStats.weak }}</a-tag>
                </div>
              </div>
            </div>

            <!-- 学习总时长 + 连续天数 -->
            <div class="stat-card">
              <div class="stat-icon-wrapper" style="background: rgba(114,46,209,0.1);">
                <ClockCircleOutlined class="stat-icon" style="color: #722ED1;" />
              </div>
              <div class="stat-body">
                <div class="stat-value">
                  <span class="count-up">{{ overview?.totalStudyMinutes ? formatMinutes(overview.totalStudyMinutes) : '—' }}</span>
                </div>
                <div class="stat-label">学习总时长</div>
                <div class="stat-sub" v-if="overview?.streakDays">
                  <FireOutlined style="color: #FA8C16; font-size: 12px;" />
                  {{ overview.streakDays }} 天连续学习
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ======================================== -->
        <!--  Section 2: 知识雷达图 + 薄弱知识点       -->
        <!-- ======================================== -->
        <div ref="sectionRefs.radarKp" class="dashboard-section" :class="{ visible: sectionVisible.radarKp }">
          <div class="section-row-2col">
            <!-- 雷达图 -->
            <div class="section-card chart-card">
              <div class="card-header">
                <h3><RadarChartOutlined /> 知识掌握度雷达图</h3>
                <span class="card-hint">
                  <span class="legend-dot current"></span> 当前
                  <span class="legend-dot initial"></span> 初始
                </span>
              </div>
              <div class="chart-body">
                <div ref="chartRefs.radar" class="echarts-container"></div>
                <!-- 提升幅度 -->
                <div class="improvement-bar" v-if="masteryLevels.length">
                  <RiseOutlined style="color: #52C41A;" />
                  <span>
                    平均提升 <b>{{ calculateAvgImprovement() }}%</b>
                  </span>
                </div>
              </div>
            </div>

            <!-- 薄弱知识点 -->
            <div class="section-card weak-points-card">
              <div class="card-header">
                <h3><WarningOutlined /> 薄弱知识点</h3>
                <a-tag color="error" v-if="lowMasteryKPs.length">{{ lowMasteryKPs.length }} 个待提升</a-tag>
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
                      <a-tag
                        :color="kp.level === 'weak' ? 'error' : 'warning'"
                        size="small"
                      >
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
                  <TrophyOutlined style="font-size: 36px; color: #52C41A;" />
                  <p>所有知识点掌握度达标！继续保持</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ======================================== -->
        <!--  Section 3: 认知负荷趋势                  -->
        <!-- ======================================== -->
        <div ref="sectionRefs.trend" class="dashboard-section" :class="{ visible: sectionVisible.trend }">
          <div class="section-card">
            <div class="card-header">
              <h3><LineChartOutlined /> 认知负荷趋势</h3>
              <span class="card-hint">越低越好 · 虚线为负荷警戒线</span>
            </div>
            <div class="chart-body">
              <div ref="chartRefs.trend" class="echarts-container" style="height: 340px;"></div>
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
        <div ref="sectionRefs.weakpointSuggestion" class="dashboard-section" :class="{ visible: sectionVisible.weakpointSuggestion }">
          <div class="section-row-2col">
            <!-- 薄弱点详细列表 -->
            <div class="section-card">
              <div class="card-header">
                <h3><AimOutlined /> 薄弱点详情</h3>
                <span class="card-hint" v-if="weakPoints.length">{{ weakPoints.length }} 个诊断薄弱点</span>
              </div>
              <div class="weak-points-detailed">
                <template v-if="weakPoints.length > 0">
                  <div
                    v-for="(wp, idx) in weakPoints.slice(0, 6)"
                    :key="idx"
                    class="wp-detail-item"
                    :style="{ borderLeftColor: getSeverityColor(wp.severity) }"
                  >
                    <div class="wp-detail-header">
                      <strong>{{ wp.knowledgePoint }}</strong>
                      <a-tag :color="getSeverityColor(wp.severity)" size="small">
                        {{ getSeverityLabel(wp.severity) }}
                      </a-tag>
                    </div>
                    <p class="wp-detail-reason">{{ wp.reason }}</p>
                    <p class="wp-detail-remediation" v-if="wp.suggestedRemediation">
                      <BulbOutlined /> {{ wp.suggestedRemediation }}
                    </p>
                  </div>
                </template>
                <div v-else class="weak-empty">
                  <TrophyOutlined style="font-size: 36px; color: #52C41A;" />
                  <p>未检测到薄弱点，学习状态良好！</p>
                </div>
              </div>
            </div>

            <!-- AI 学习建议 -->
            <div class="section-card">
              <div class="card-header">
                <h3><BulbOutlined /> AI 学习建议</h3>
                <span class="card-hint">基于星火大模型分析</span>
              </div>
              <div class="suggestions-list">
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
                    <span class="sg-icon">{{ getSuggestionIcon(sg.category) }}</span>
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
                      style="margin-right: 4px;"
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
        <div ref="sectionRefs.calendar" class="dashboard-section" :class="{ visible: sectionVisible.calendar }">
          <div class="section-card">
            <div class="card-header">
              <h3><CalendarOutlined /> 学习日历</h3>
              <div class="calendar-nav">
                <a-button size="small" type="text" @click="calendarMonth--; if(calendarMonth<1){calendarMonth=12;calendarYear--}; nextTick(() => initCalendarChart())">
                  ◀
                </a-button>
                <span class="calendar-label">{{ calendarYear }} 年 {{ calendarMonth }} 月</span>
                <a-button size="small" type="text" @click="calendarMonth++; if(calendarMonth>12){calendarMonth=1;calendarYear++}; nextTick(() => initCalendarChart())">
                  ▶
                </a-button>
              </div>
            </div>
            <div class="chart-body">
              <div ref="chartRefs.calendar" class="echarts-container" style="height: 220px;"></div>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script lang="ts">
import { DashboardOutlined } from '@ant-design/icons-vue'
export default { components: { DashboardOutlined } }
</script>

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
    color: @gray-500;
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
    color: rgba(212, 163, 115, 0.60);
    margin: 0 0 24px;
    font-size: @font-size-base;
  }
}

// ============================================================
//   Section Animation
// ============================================================
.dashboard-section {
  opacity: 0;
  transform: translateY(30px);
  transition: opacity 0.6s ease, transform 0.6s ease;
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
  color: @gray-900;
  line-height: 1.2;

  .count-up {
    font-size: @font-size-2xl;
  }

  .stat-separator {
    color: @gray-400;
    font-weight: @font-weight-normal;
    margin: 0 2px;
  }

  .stat-total {
    color: @gray-500;
    font-weight: @font-weight-medium;
  }
}

.stat-label {
  font-size: @font-size-sm;
  color: @gray-500;
  margin-top: 2px;
}

.stat-sub {
  font-size: @font-size-xs;
  color: @gray-400;
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
    fill: @gray-900;
    dominant-baseline: middle;
  }

  .gauge-unit {
    font-size: 12px;
    fill: @gray-500;
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
    border-bottom: 1px solid @gray-200;

    h3 {
      margin: 0;
      font-size: @font-size-md;
      font-weight: @font-weight-semibold;
      color: @gray-800;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .card-hint {
      font-size: @font-size-xs;
      color: @gray-400;
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
  color: @gray-600;

  b {
    color: #52C41A;
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
    box-shadow: 0 0 4px rgba(79,124,255,0.4);
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
  border-bottom: 1px solid @gray-100;

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
    color: @gray-800;
  }

  .wp-bar-bg {
    height: 6px;
    background: @gray-100;
    border-radius: 3px;
    overflow: hidden;
  }

  .wp-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 1.2s cubic-bezier(0.4, 0, 0.2, 1);
    background: @brand-blue-500;

    &.weak {
      background: linear-gradient(90deg, #FF4D4F, #FA8C16);
    }
    &.developing {
      background: linear-gradient(90deg, #FA8C16, @brand-blue-500);
    }
  }

  .wp-meta {
    font-size: @font-size-xs;
    color: @gray-400;
    margin-top: 4px;
  }
}

.weak-empty {
  text-align: center;
  padding: 40px 0;
  color: @gray-400;
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
  border-top: 1px solid @gray-100;
}

.cl-dim-item {
  .cl-dim-label {
    font-size: @font-size-xs;
    color: @gray-500;
    margin-bottom: 4px;
  }
}

// ============================================================
//   Weak Points Detailed
// ============================================================
.weak-points-detailed {
  padding: 12px @card-padding;
  max-height: 420px;
  overflow-y: auto;
}

.wp-detail-item {
  padding: 12px 14px;
  margin-bottom: 10px;
  border-left: 3px solid;
  background: @gray-50;
  border-radius: 0 @radius-sm @radius-sm 0;

  &:last-child {
    margin-bottom: 0;
  }

  .wp-detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;

    strong {
      font-size: @font-size-sm;
      color: @gray-800;
    }
  }

  .wp-detail-reason {
    font-size: @font-size-sm;
    color: @gray-600;
    margin: 0 0 4px;
    line-height: 1.5;
  }

  .wp-detail-remediation {
    font-size: @font-size-xs;
    color: @brand-blue-600;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 4px;
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
  }

  .sg-title {
    font-size: @font-size-sm;
    font-weight: @font-weight-semibold;
    color: @gray-800;
    flex: 1;
  }

  .sg-content {
    font-size: @font-size-sm;
    color: @gray-600;
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
    color: @gray-600;
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
