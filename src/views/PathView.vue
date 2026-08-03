<script setup lang="ts">
/**
 * 我的学习路径 页面
 *
 * 区域：
 *   1. 概览卡片（关键指标 + 认知负荷仪表盘 + 完成进度）
 *   2. 学习路径展示（复用 LearningPathView：Gantt + 时间轴 + 路径切换）
 *   3. 每日详情面板（点击甘特图某天展开）
 *   4. AOO 寻优回放（折叠面板 + ECharts 收敛动画）
 *   5. 操作按钮行（重新规划 / 导出 / 分享）
 */
import { ref, computed, onMounted, onUnmounted, watch, nextTick, reactive } from 'vue'
import { useIsMobile } from '@/composables/useIsMobile'
import { useRouter, useRoute } from 'vue-router'
import * as echarts from 'echarts'
import { usePathStore } from '@/stores/path'
import { useDiagnosisStore } from '@/stores/diagnosis'
import { diagnosisApi } from '@/api/modules/diagnosis'
import { pathApi } from '@/api/modules/path'
import LearningPathView from '@/components/LearningPathView.vue'
import SeedTrajectory from '@/components/SeedTrajectory.vue'
import type { LearningTask, DailyTaskView } from '@/types'
import {
  NodeIndexOutlined,
  ThunderboltOutlined,
  ReloadOutlined,
  DownloadOutlined,
  ShareAltOutlined,
  ClockCircleOutlined,
  BookOutlined,
  CalendarOutlined,
  TrophyOutlined,
  BarChartOutlined,
  CaretRightOutlined,
  CheckCircleOutlined,
  CloseOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  FieldTimeOutlined,
  DashboardOutlined,
  RightOutlined,
  LeftOutlined,
  ExperimentOutlined,
  SettingOutlined,
  AimOutlined,
  DiffOutlined,
  CheckOutlined,
  PlusCircleOutlined,
  MinusCircleOutlined,
  SwapOutlined,
  BulbOutlined
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

// ============================================================
//   Store & Router
// ============================================================
const router = useRouter()
const route = useRoute()
const pathStore = usePathStore()
const diagnosisStore = useDiagnosisStore()

// 移动端断点
const { isMobile } = useIsMobile()

// ============================================================
//   基础 State
// ============================================================
const loading = ref(false)
const regenerating = ref(false)

// ============================================================
//   任务完成状态（本地管理）
// ============================================================
const completedTasks = reactive<Set<string>>(new Set())

function toggleTaskComplete(taskId: string) {
  if (completedTasks.has(taskId)) {
    completedTasks.delete(taskId)
  } else {
    completedTasks.add(taskId)
  }
}

function isTaskCompleted(taskId: string): boolean {
  return completedTasks.has(taskId)
}

// ============================================================
//   概览数据
// ============================================================
const hasPath = computed(() => pathStore.hasPath)
const pathId = computed(() => pathStore.pathId)
const isGenerating = computed(() => pathStore.isGenerating)
const generationProgress = computed(() => pathStore.generationProgress)
const error = computed(() => pathStore.error)

const currentPath = computed(() => pathStore.currentPath)
const totalDays = computed(() => pathStore.totalDays)
const totalTasks = computed(() => pathStore.taskCount)
const totalHours = computed(() => pathStore.estimatedHours)
const optimizationScore = computed(() => pathStore.optimizationScore)
const difficultyCurve = computed(() => pathStore.difficultyCurve)

/** 总完成百分比 */
const completionPercent = computed(() => {
  if (!currentPath.value) return 0
  const all = currentPath.value.dailyTasks.flat()
  if (all.length === 0) return 0
  const done = all.filter((t: LearningTask) => completedTasks.has(t.id)).length
  return Math.round((done / all.length) * 100)
})

/** 认知负荷指数（基于难度曲线均值映射 0-100） */
const cognitiveLoadIndex = computed(() => {
  const curve = difficultyCurve.value
  if (!curve || curve.length === 0) return 0
  const avg = curve.reduce((s: number, v: number) => s + v, 0) / curve.length
  return Math.round((avg / 5) * 100)
})

// ============================================================
//   P2 待采纳重规划版本（对话触发生成的新版本）
// ============================================================
const pendingPath = ref<import('@/api/modules/path').PendingPath | null>(null)
const pendingLoading = ref(false)
const adopting = ref(false)
const diffVisible = ref(false)

async function loadPendingPath() {
  pendingLoading.value = true
  try {
    const p = await pathApi.getPendingPath()
    pendingPath.value = p
  } catch (e) {
    pendingPath.value = null
  } finally {
    pendingLoading.value = false
  }
}

async function handleAdopt() {
  if (!pendingPath.value) return
  adopting.value = true
  try {
    await pathApi.adoptPath(pendingPath.value.path_id)
    message.success(`已采纳学习路径 v${pendingPath.value.version}`)
    pendingPath.value = null
    // 刷新当前路径
    await refreshPath()
  } catch (e) {
    message.error('采纳失败，请稍后重试')
  } finally {
    adopting.value = false
  }
}

async function refreshPath() {
  loading.value = true
  try {
    await pathStore.fetchCurrentPath()
  } finally {
    loading.value = false
  }
}

/** 认知负荷等级 */
const cognitiveLoadLevel = computed(() => {
  const v = cognitiveLoadIndex.value
  if (v < 35) return { label: '较低', color: '#52C41A' }
  if (v < 65) return { label: '适中', color: '#FA8C16' }
  return { label: '较高', color: '#FF4D4F' }
})

/** dailyTaskViews 来自 store */
const dailyViews = computed(() => pathStore.dailyTaskViews)

/** 当前覆盖的知识点数 */
const coveredKnowledgePoints = computed(() => {
  const set = new Set<string>()
  currentPath.value?.dailyTasks.forEach((day) =>
    day.forEach((t: LearningTask) => set.add(t.knowledgePoint))
  )
  return set.size
})

/** 日均学习时长（小时） */
const avgDailyHours = computed(() => {
  if (totalDays.value === 0) return 0
  return (totalHours.value / totalDays.value).toFixed(1)
})

// ============================================================
//   每日详情
// ============================================================
const selectedDayIndex = ref<number | null>(null)
const selectedDay = computed<DailyTaskView | null>(() => {
  if (selectedDayIndex.value === null) return null
  return dailyViews.value.find((d) => d.dayIndex === selectedDayIndex.value) ?? null
})

function handleTaskClick(task: LearningTask) {
  selectedDayIndex.value = task.dayIndex
  // 滚动到详情区
  nextTick(() => {
    const el = document.getElementById('daily-detail-panel')
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function closeDayDetail() {
  selectedDayIndex.value = null
}

function goToDay(dir: -1 | 1) {
  if (selectedDayIndex.value === null) return
  const next = selectedDayIndex.value + dir
  if (next >= 1 && next <= totalDays.value) {
    selectedDayIndex.value = next
  }
}

// ============================================================
//   路径变体切换
// ============================================================
const variantLabels = ['当前方案', '速成冲刺', '稳扎稳打', '查漏补缺']
const variantIcons = [SettingOutlined, ThunderboltOutlined, FieldTimeOutlined, ExperimentOutlined]
const activeVariantIndex = ref(0)

async function handleVariantChange(pathId: string, index: number) {
  activeVariantIndex.value = index
  if (index > 0) {
    await pathStore.selectAlternativePath(pathId)
  }
}
// 备选路径数
const alternativeCount = computed(() => pathStore.alternativePaths.length)

// ============================================================
//   AOO 收敛回放
// ============================================================
const convergenceExpanded = ref(false)
const convergenceChartRef = ref<HTMLDivElement | null>(null)
const isPlaying = ref(false)
const currentFrame = ref(0)
/** 收敛视图 Tab: 'curve' = 收敛曲线, 'trajectory' = 粒子轨迹 */
const convergenceTab = ref<'curve' | 'trajectory'>('curve')
let chartInstance: echarts.ECharts | null = null
let playTimer: ReturnType<typeof setInterval> | null = null
let resizeObserver: ResizeObserver | null = null

const convergenceData = computed(() => pathStore.convergenceData)
const hasConvergence = computed(() => pathStore.hasConvergenceData)
/** 是否包含粒子快照数据（用于展示 SeedTrajectory） */
const hasPopulationSnapshots = computed(() => {
  const data = convergenceData.value
  return !!(data?.populationSnapshots && data.populationSnapshots.length > 0)
})

const totalFrames = computed(() => convergenceData.value?.iterations?.length ?? 0)

/** 当前帧标注的数据集 */
const revealedIterations = computed(() => {
  const data = convergenceData.value
  if (!data || !data.iterations)
    return { x: [] as number[], best: [] as number[], avg: [] as number[] }
  const end = currentFrame.value || data.iterations.length
  return {
    x: data.iterations.slice(0, end),
    best: (data.bestFitness || []).slice(0, end),
    avg: (data.avgFitness || []).slice(0, end)
  }
})

/**
 * 初始化（或重建）收敛曲线图表。
 *
 * 注意：图表容器位于 `v-if="convergenceTab === 'curve'"` 内部，
 * 切到「粒子轨迹」再切回来时 DOM 节点会被销毁并重建。
 * 若继续复用旧的 ECharts 实例，它绑定的是已脱离文档的旧节点，
 * 画面就会一片空白。因此这里始终以「当前真实节点」为准重建实例。
 */
function initConvergenceChart() {
  const el = convergenceChartRef.value
  if (!el) return

  // 释放可能存在的旧实例 / 旧监听，避免内存泄漏与错误复用
  disposeConvergenceChart()

  chartInstance = echarts.init(el)
  resizeObserver = new ResizeObserver(() => chartInstance?.resize())
  resizeObserver.observe(el)

  renderConvergenceChart()
}

/** 销毁收敛曲线图表实例与其尺寸监听 */
function disposeConvergenceChart() {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
}

/**
 * 确保图表实例与当前 DOM 节点一致；不一致则重建。
 * 用于 Tab 切换、面板展开等场景。
 */
function ensureConvergenceChart() {
  const el = convergenceChartRef.value
  if (!el) return
  // getInstanceByDom 拿不到，说明该节点尚未绑定实例（DOM 被重建过）
  const bound = echarts.getInstanceByDom(el)
  if (!bound || bound !== chartInstance || chartInstance?.isDisposed()) {
    initConvergenceChart()
  } else {
    chartInstance.resize()
    renderConvergenceChart()
  }
}

function renderConvergenceChart() {
  if (!chartInstance || !convergenceData.value) return
  const cd = convergenceData.value
  const revealed = revealedIterations.value

  const option: echarts.EChartsOption = {
    animation: true,
    animationDuration: 400,
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(10,13,20,0.95)',
      borderColor: 'rgba(212,163,115,0.20)',
      textStyle: { color: '#F8FAFC', fontSize: 13 }
    },
    legend: {
      data: ['最优适应度', '平均适应度'],
      top: 0,
      right: 10,
      textStyle: { fontSize: 12, color: '#CBD5E1' }
    },
    grid: { top: 44, right: 30, bottom: 56, left: 64 },
    xAxis: {
      type: 'value',
      name: '迭代次数',
      nameLocation: 'middle',
      nameGap: 32,
      nameTextStyle: { fontSize: 12, color: '#CBD5E1', fontWeight: 500 },
      min: 0,
      max: cd.iterations?.length ?? 100,
      axisLabel: { fontSize: 11, color: '#94A3B8' },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.18)' } },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } }
    },
    yAxis: {
      type: 'value',
      // 纵轴恢复常规方向：数值自下而上递增
      inverse: false,
      name: '适应度',
      nameLocation: 'middle',
      nameGap: 44,
      nameTextStyle: { fontSize: 12, color: '#CBD5E1', fontWeight: 500 },
      axisLabel: { fontSize: 11, color: '#94A3B8' },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.18)' } },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      min: (val: { min: number }) => Math.floor(val.min * 0.98),
      max: (val: { max: number }) => Math.ceil(val.max * 1.02)
    },
    series: [
      {
        name: '最优适应度',
        type: 'line',
        data: revealed.best.map((v, i) => [revealed.x[i], v]),
        smooth: true,
        lineStyle: { color: '#D4A373', width: 1.5 },
        itemStyle: { color: '#D4A373' },
        symbol: 'none',
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(212,163,115,0.15)' },
            { offset: 1, color: 'rgba(212,163,115,0.02)' }
          ])
        }
      },
      {
        name: '平均适应度',
        type: 'line',
        data: revealed.avg.map((v, i) => [revealed.x[i], v]),
        smooth: true,
        lineStyle: { color: '#4A6CF7', width: 1.2, type: 'dashed' },
        itemStyle: { color: '#4A6CF7' },
        symbol: 'none'
      }
    ]
  }

  chartInstance.setOption(option, true)
}

watch(currentFrame, () => renderConvergenceChart())

function togglePlay() {
  if (isPlaying.value) {
    pausePlayback()
  } else {
    startPlayback()
  }
}

function startPlayback() {
  if (currentFrame.value >= totalFrames.value) {
    currentFrame.value = 0
  }
  isPlaying.value = true
  playTimer = setInterval(() => {
    if (currentFrame.value < totalFrames.value) {
      currentFrame.value++
    } else {
      pausePlayback()
    }
  }, 80)
}

function pausePlayback() {
  isPlaying.value = false
  if (playTimer) {
    clearInterval(playTimer)
    playTimer = null
  }
}

function resetPlayback() {
  pausePlayback()
  currentFrame.value = 0
}

/**
 * a-collapse 面板展开/折叠回调。
 *
 * activeKey 是单向绑定（三元表达式不能用于 v-model），
 * 因此必须在这里手动同步 convergenceExpanded，
 * 否则点击标题栏没有任何反应 —— 回放区永远打不开。
 */
function onConvergenceCollapseChange(keys: string | string[]): void {
  const arr = Array.isArray(keys) ? keys : keys ? [keys] : []
  convergenceExpanded.value = arr.includes('1')
}

watch(convergenceExpanded, (val) => {
  if (val) {
    nextTick(() => ensureConvergenceChart())
  } else {
    pausePlayback()
  }
})

// 切换「收敛曲线 / 粒子轨迹」时，曲线容器会被 v-if 销毁重建，
// 切回来必须重新绑定实例，否则图表不显示。
watch(convergenceTab, (tab) => {
  if (tab === 'curve') {
    nextTick(() => ensureConvergenceChart())
  } else {
    // 离开曲线视图时暂停回放并释放实例，避免持有失效 DOM
    pausePlayback()
    disposeConvergenceChart()
  }
})

// 数据是异步到达的（AOO 轮询完成后才写入 store）。
// 若此时面板已展开，需要重新渲染，否则图表停留在空状态。
watch(
  () => pathStore.convergenceData,
  (val) => {
    if (!val?.iterations?.length) return
    currentFrame.value = 0
    if (!convergenceExpanded.value || convergenceTab.value !== 'curve') return
    nextTick(() => ensureConvergenceChart())
  }
)

// ============================================================
//   操作按钮
// ============================================================
async function handleRegenerate(diagnosisId?: string | number) {
  // ── 获取有效的 diagnosis_id ──
  let diagId = diagnosisId

  // 1. 如果未指定，尝试使用当前路径已有的 diagnosisId
  if (!diagId) {
    diagId = currentPath.value?.diagnosisId || ''
  }

  // 2. 如果当前路径没有 diagnosisId，尝试从诊断 Store 获取 (persisted)
  if (!diagId) {
    diagId = diagnosisStore.currentDiagnosis?.id || ''
  }

  // 3. 如果还没有，从 API 获取最新诊断结果
  if (!diagId) {
    try {
      const latest = await diagnosisApi.getLatest()
      if (latest?.id) {
        diagId = latest.id
      }
    } catch {
      // 忽略查询失败，下面会统一处理
    }
  }

  // 4. 最终校验
  if (!diagId) {
    message.warning('暂无可用的诊断结果，请先完成认知诊断测评')
    return
  }

  regenerating.value = true
  try {
    await pathStore.generatePath(String(diagId))
    message.success('学习路径已启动生成，请稍候...')
  } catch {
    message.error('重新生成失败，请稍后重试')
  } finally {
    regenerating.value = false
  }
}

// ── 重新规划：选择诊断历史 ──
const replanModalVisible = ref(false)
const replanLoading = ref(false)
const replanUseChat = ref(false)
const replanHistory = ref<ReplanDiagItem[]>([])

interface ReplanDiagItem {
  id: string | number
  created_at: string
  score: number
  mastery: number
  weak_points: string[]
}

async function openReplanModal() {
  replanModalVisible.value = true
  replanLoading.value = true
  replanHistory.value = []
  try {
    const list = await diagnosisApi.getHistory()
    replanHistory.value = Array.isArray(list)
      ? (list as ReplanDiagItem[]).slice().reverse()
      : []
  } catch {
    message.warning('获取诊断历史失败，请稍后重试')
  } finally {
    replanLoading.value = false
  }
}

function confirmReplan(item: ReplanDiagItem) {
  replanModalVisible.value = false
  // 若勾选「叠加对话分析」→ 诊断 + 对话画像融合重规划；否则纯诊断重规划
  if (replanUseChat.value) {
    regenerating.value = true
    pathStore
      .regeneratePathFlexible(String(item.id), true)
      .then((ok) => {
        if (ok) message.success('已基于「诊断 + 对话分析」启动重规划')
      })
      .catch(() => message.error('重规划启动失败，请稍后重试'))
      .finally(() => (regenerating.value = false))
  } else {
    handleRegenerate(item.id)
  }
}

function handleExport() {
  message.info('导出功能开发中，即将支持 PDF / 图片导出')
}

function handleShare() {
  const url = `${window.location.origin}/share/path/${pathId.value}`
  navigator.clipboard.writeText(url).then(
    () => message.success('分享链接已复制到剪贴板'),
    () => message.warning('复制失败，请手动复制地址栏链接')
  )
}

function goToDiagnose() {
  router.push('/diagnose')
}

// ============================================================
//   格式化
// ============================================================
function formatDate(iso: string | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const TASK_TYPE_LABELS: Record<string, string> = {
  video: '视频',
  quiz: '测验',
  reading: '阅读',
  article: '阅读',
  project: '项目',
  exercise: '练习'
}
const TASK_TYPE_COLORS: Record<string, string> = {
  video: '#1890FF',
  quiz: '#FA8C16',
  reading: '#52C41A',
  article: '#52C41A',
  project: '#722ED1',
  exercise: '#13C2C2'
}

// ============================================================
//   生命周期
// ============================================================
onMounted(async () => {
  loading.value = true
  try {
    // 若从「我的记录」带 ?id= 打开指定历史路径，则加载该路径
    const targetId = route.query['id'] as string | undefined
    if (targetId) {
      try {
        const target = await pathApi.getPath(targetId)
        pathStore.currentPath = target
        return
      } catch (e) {
        // 加载失败回退到当前活跃路径
      }
    }
    // 总是从 API 获取最新路径数据，避免持久化过期数据导致渲染异常
    await pathStore.fetchCurrentPath()
  } finally {
    loading.value = false
  }
  // P2: 检查是否有对话触发生成的待采纳重规划版本
  await loadPendingPath()
})

onUnmounted(() => {
  pausePlayback()
  disposeConvergenceChart()
  // 清理轮询定时器，防止页面切换后僵尸轮询
  pathStore.dispose()
})
</script>

<template>
  <div class="path-page">
    <!-- =========================================================
         1. 页面头部 + 操作按钮
         ========================================================= -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">
          <NodeIndexOutlined class="title-icon" />
          我的学习路径
        </h1>
      </div>
      <div class="header-right" v-if="hasPath && !isGenerating">
        <a-button class="action-btn" :loading="regenerating" @click="openReplanModal">
          <ReloadOutlined /> 重新规划
        </a-button>
        <a-button class="action-btn" @click="handleExport">
          <DownloadOutlined /> 导出路径
        </a-button>
        <a-button class="action-btn" type="primary" ghost @click="handleShare">
          <ShareAltOutlined /> 分享路径
        </a-button>
      </div>
    </div>

    <!-- =========================================================
         P2 待采纳重规划版本（对话触发生成，需用户一键采纳）
         ========================================================= -->
    <div
      v-if="pendingPath && !isGenerating"
      class="pending-banner"
    >
      <div class="pending-icon"><ExperimentOutlined /></div>
      <div class="pending-body">
        <div class="pending-title">
          检测到新版本学习路径 v{{ pendingPath.version }}
          <a-tag color="gold" class="pending-tag">待采纳</a-tag>
        </div>
        <div class="pending-desc">
          {{ pendingPath.diff?.summary || '对话触发了路径重规划，点击查看变更详情' }}
          <span class="pending-meta">
            · {{ pendingPath.total_days }} 天 · {{ pendingPath.task_count }} 个任务
            · 适应度 {{ (pendingPath.fitness_score ?? 0).toFixed(2) }}
          </span>
        </div>
        <div v-if="pendingPath.explanation" class="pending-explanation">
          <BulbOutlined class="explain-icon" />
          <span>{{ pendingPath.explanation }}</span>
        </div>
      </div>
      <div class="pending-actions">
        <a-button size="small" @click="diffVisible = true">
          <DiffOutlined /> 查看变更
        </a-button>
        <a-button
          type="primary"
          size="small"
          :loading="adopting"
          @click="handleAdopt"
        >
          <CheckOutlined /> 一键采纳
        </a-button>
      </div>
    </div>

    <!-- =========================================================
         生成中 / 失败 / 空 / 加载 状态
         ========================================================= -->
    <div v-if="isGenerating" class="state-card generating">
      <div class="generating-inner">
        <div class="spin-icon"><ThunderboltOutlined /></div>
        <a-spin size="large" />
        <h3>AOO 引擎正在优化学习路径</h3>
        <p>分析知识点图谱 · 评估认知负荷 · 计算最优调度</p>
        <a-progress
          :percent="generationProgress"
          :stroke-color="{ from: '#4F7CFF', to: '#52C41A' }"
          class="generating-progress"
        />
      </div>
    </div>

    <div v-else-if="error" class="state-card error">
      <a-result status="error" title="路径生成失败" :sub-title="error">
        <template #extra>
          <a-button type="primary" @click="handleRegenerate">
            <ThunderboltOutlined /> 重新生成
          </a-button>
        </template>
      </a-result>
    </div>

    <div v-else-if="!hasPath && !loading" class="state-card empty">
      <a-result title="尚未生成学习路径">
        <template #icon><NodeIndexOutlined style="color: #9b8a7a; font-size: 64px" /></template>
        <template #sub-title>完成认知诊断后，AOO 引擎将为你量身定制专属学习路径</template>
        <template #extra>
          <a-space direction="vertical">
            <a-button type="primary" size="large" :loading="regenerating" @click="handleRegenerate">
              <ThunderboltOutlined /> 生成学习路径
            </a-button>
            <a-button size="large" @click="goToDiagnose">前往认知诊断</a-button>
          </a-space>
        </template>
      </a-result>
    </div>

    <div v-else-if="loading" class="state-card">
      <a-spin size="large" tip="加载学习路径..." />
    </div>

    <!-- =========================================================
         2. 概览卡片区
         ========================================================= -->
    <template v-if="hasPath && !isGenerating">
      <div class="overview-grid">
        <!-- 路径信息卡片 -->
        <div class="overview-card overview-card--info">
          <div class="overview-card-header">
            <div class="overview-card-icon" style="background: #eff3ff; color: #4f7cff">
              <CalendarOutlined />
            </div>
            <div>
              <div class="overview-card-label">当前路径</div>
              <div class="overview-card-title">AOO 智能推荐方案</div>
            </div>
          </div>
          <div class="overview-card-meta">
            <span>生成于 {{ formatDate(currentPath?.createdAt) }}</span>
            <span v-if="currentPath?.metadata?.generationTime">
              耗时 {{ currentPath.metadata.generationTime.toFixed(1) }}s
            </span>
          </div>
        </div>

        <!-- 总天数 -->
        <div class="overview-card overview-card--metric">
          <div class="overview-card-icon" style="background: #e6f4ff; color: #1677ff">
            <CalendarOutlined />
          </div>
          <div class="overview-metric-value">{{ totalDays }}</div>
          <div class="overview-metric-label">总天数</div>
        </div>

        <!-- 总任务数 -->
        <div class="overview-card overview-card--metric">
          <div class="overview-card-icon" style="background: #f6ffed; color: #52c41a">
            <BookOutlined />
          </div>
          <div class="overview-metric-value">{{ totalTasks }}</div>
          <div class="overview-metric-label">总任务数</div>
        </div>

        <!-- 总时长 -->
        <div class="overview-card overview-card--metric">
          <div
            class="overview-card-icon"
            style="background: rgba(251, 191, 36, 0.12); color: #fbbf24"
          >
            <ClockCircleOutlined />
          </div>
          <div class="overview-metric-value">
            {{ totalHours }}<span class="metric-unit">h</span>
          </div>
          <div class="overview-metric-label">预计总时长</div>
        </div>

        <!-- 认知负荷仪表盘 -->
        <div class="overview-card overview-card--gauge">
          <div
            class="overview-card-icon"
            style="background: rgba(248, 113, 113, 0.12); color: #f87171"
          >
            <DashboardOutlined />
          </div>
          <div class="gauge-wrap">
            <!-- SVG 仪表盘 -->
            <svg viewBox="0 0 100 60" class="gauge-svg">
              <!-- 底色弧 -->
              <path
                d="M 12 52 A 38 38 0 0 1 88 52"
                fill="none"
                stroke="#F0F0F0"
                stroke-width="10"
                stroke-linecap="round"
              />
              <!-- 值弧 -->
              <path
                d="M 12 52 A 38 38 0 0 1 88 52"
                fill="none"
                :stroke="cognitiveLoadLevel.color"
                stroke-width="10"
                stroke-linecap="round"
                :stroke-dasharray="`${cognitiveLoadIndex * 1.19} 200`"
                class="gauge-value-arc"
              />
              <!-- 指针 -->
              <line
                x1="50"
                y1="52"
                :x2="50 + 35 * Math.cos(Math.PI - (cognitiveLoadIndex / 100) * Math.PI)"
                :y2="52 - 35 * Math.sin(Math.PI - (cognitiveLoadIndex / 100) * Math.PI)"
                :stroke="cognitiveLoadLevel.color"
                stroke-width="2"
                stroke-linecap="round"
              />
              <circle cx="50" cy="52" r="3" fill="#3D3B39" />
            </svg>
            <div class="gauge-value" :style="{ color: cognitiveLoadLevel.color }">
              {{ cognitiveLoadIndex }}
            </div>
          </div>
          <div class="overview-metric-label">认知负荷 · {{ cognitiveLoadLevel.label }}</div>
        </div>

        <!-- 完成进度 -->
        <div class="overview-card overview-card--progress">
          <div class="overview-card-icon" style="background: #f9f0ff; color: #722ed1">
            <TrophyOutlined />
          </div>
          <div class="progress-circle-wrap">
            <!-- SVG 环形进度 -->
            <svg viewBox="0 0 100 100" class="progress-circle-svg">
              <circle cx="50" cy="50" r="38" fill="none" stroke="#F0F0F0" stroke-width="8" />
              <circle
                cx="50"
                cy="50"
                r="38"
                fill="none"
                stroke="#722ED1"
                stroke-width="8"
                stroke-linecap="round"
                :stroke-dasharray="`${completionPercent * 2.388} 400`"
                transform="rotate(-90 50 50)"
                class="progress-circle-arc"
              />
            </svg>
            <div class="progress-circle-text">
              <span class="progress-circle-value">{{ completionPercent }}</span>
              <span class="progress-circle-unit">%</span>
            </div>
          </div>
          <div class="overview-metric-label">路径完成度</div>
        </div>

        <!-- 覆盖知识点 + 日均 -->
        <div class="overview-card overview-card--extras">
          <div class="extra-row">
            <div class="extra-item">
              <div class="extra-value">{{ coveredKnowledgePoints }}</div>
              <div class="extra-label">覆盖知识点</div>
            </div>
            <div class="extra-divider" />
            <div class="extra-item">
              <div class="extra-value">{{ avgDailyHours }}<span class="metric-unit">h</span></div>
              <div class="extra-label">日均学习</div>
            </div>
            <div class="extra-divider" />
            <div class="extra-item">
              <div class="extra-value">{{ optimizationScore }}</div>
              <div class="extra-label">优化得分</div>
            </div>
          </div>
        </div>
      </div>

      <!-- =========================================================
           3. 路径切换 Tabs
           ========================================================= -->
      <div class="variant-tabs" v-if="alternativeCount > 0">
        <button
          v-for="(label, idx) in variantLabels.slice(0, 1 + alternativeCount)"
          :key="idx"
          class="variant-tab"
          :class="{ 'is-active': activeVariantIndex === idx }"
          @click="
            handleVariantChange(
              idx === 0 ? (currentPath?.id ?? '') : (pathStore.alternativePaths[idx - 1]?.id ?? ''),
              idx
            )
          "
        >
          <component :is="variantIcons[idx]" class="variant-tab-icon" />
          <span>{{ label }}</span>
          <span v-if="idx === 0" class="variant-tag current">当前</span>
        </button>
      </div>

      <!-- =========================================================
           4. 甘特图 / 时间轴 主视图
           ========================================================= -->
      <LearningPathView
        :key="(pathId ?? '') + activeVariantIndex"
        :show-stats="false"
        :show-variants="false"
        :show-legend="true"
        :height="'auto'"
        initial-view="gantt"
        @task-click="handleTaskClick"
      />

      <!-- =========================================================
           5. 每日详情面板
           ========================================================= -->
      <div v-if="selectedDay" id="daily-detail-panel" class="daily-detail">
        <div class="daily-detail-header">
          <div class="daily-detail-title-row">
            <button
              class="daily-nav-btn"
              @click="goToDay(-1)"
              :disabled="selectedDay.dayIndex <= 1"
            >
              <LeftOutlined />
            </button>
            <h3 class="daily-detail-title">{{ selectedDay.dayLabel }} · {{ selectedDay.date }}</h3>
            <button
              class="daily-nav-btn"
              @click="goToDay(1)"
              :disabled="selectedDay.dayIndex >= totalDays"
            >
              <RightOutlined />
            </button>
          </div>
          <div class="daily-detail-meta">
            <span><ClockCircleOutlined /> {{ selectedDay.totalMinutes }} 分钟</span>
            <span><BarChartOutlined /> 难度 {{ selectedDay.difficulty }}</span>
            <span
              ><CheckCircleOutlined />
              {{
                selectedDay.tasks.filter((t: LearningTask) => completedTasks.has(t.id)).length
              }}/{{ selectedDay.tasks.length }} 已完成
            </span>
          </div>
          <a-button type="text" size="small" @click="closeDayDetail">
            <CloseOutlined />
          </a-button>
        </div>

        <div class="daily-task-list">
          <div
            v-for="task in selectedDay.tasks"
            :key="task.id"
            class="daily-task-item"
            :class="{ 'is-completed': isTaskCompleted(task.id) }"
          >
            <div
              class="daily-task-status"
              :style="{
                borderColor: TASK_TYPE_COLORS[task.resources?.[0]?.type ?? 'reading'] || '#4F7CFF'
              }"
              @click="toggleTaskComplete(task.id)"
            >
              <CheckCircleOutlined v-if="isTaskCompleted(task.id)" />
            </div>
            <div class="daily-task-body">
              <div class="daily-task-header">
                <span class="daily-task-name">{{ task.title }}</span>
                <span
                  class="daily-task-type"
                  :style="{
                    background:
                      (TASK_TYPE_COLORS[task.resources?.[0]?.type ?? 'reading'] || '#4F7CFF') +
                      '1a',
                    color: TASK_TYPE_COLORS[task.resources?.[0]?.type ?? 'reading'] || '#4F7CFF'
                  }"
                >
                  {{ TASK_TYPE_LABELS[task.resources?.[0]?.type ?? 'reading'] || '任务' }}
                </span>
              </div>
              <p class="daily-task-desc" v-if="task.description">{{ task.description }}</p>
              <div class="daily-task-footer">
                <span class="daily-task-kp">{{ task.knowledgePoint }}</span>
                <span class="daily-task-time">
                  <ClockCircleOutlined /> {{ task.estimatedMinutes }} 分钟
                </span>
              </div>
              <!-- 学习资源 -->
              <div class="daily-task-resources" v-if="task.resources?.length">
                <a
                  v-for="res in task.resources"
                  :key="res.title"
                  class="resource-link"
                  :href="res.url || '#'"
                  target="_blank"
                >
                  <CaretRightOutlined /> {{ res.title }}
                </a>
              </div>
            </div>
            <a-button
              type="primary"
              size="small"
              class="daily-task-action"
              :ghost="isTaskCompleted(task.id)"
              @click="toggleTaskComplete(task.id)"
            >
              {{ isTaskCompleted(task.id) ? '已完成' : '开始学习' }}
            </a-button>
          </div>
        </div>
      </div>

      <!-- =========================================================
           6. AOO 寻优过程回放
           ========================================================= -->
      <div class="convergence-section" v-if="hasConvergence">
        <a-collapse
          :activeKey="convergenceExpanded ? ['1'] : []"
          :bordered="false"
          @change="onConvergenceCollapseChange"
        >
          <a-collapse-panel key="1">
            <template #header>
              <div class="convergence-header">
                <PlayCircleOutlined class="convergence-header-icon" />
                <span>AOO 寻优过程回放</span>
                <span class="convergence-header-badge" v-if="convergenceData?.metadata">
                  {{ convergenceData.metadata.populationSize }} 个体 ·
                  {{ convergenceData.metadata.convergenceRate?.toFixed(1) }}% 收敛率
                </span>
              </div>
            </template>

            <div class="convergence-body">
              <!-- Tab 切换：收敛曲线 | 粒子轨迹 -->
              <div class="convergence-tabs" v-if="hasPopulationSnapshots">
                <button
                  class="convergence-tab"
                  :class="{ 'convergence-tab--active': convergenceTab === 'curve' }"
                  @click="convergenceTab = 'curve'"
                >
                  <BarChartOutlined /> 收敛曲线
                </button>
                <button
                  class="convergence-tab"
                  :class="{ 'convergence-tab--active': convergenceTab === 'trajectory' }"
                  @click="convergenceTab = 'trajectory'"
                >
                  <AimOutlined /> 粒子轨迹
                </button>
              </div>

              <!-- 收敛曲线视图 -->
              <template v-if="convergenceTab === 'curve'">
                <div class="convergence-controls">
                  <a-button
                    :type="isPlaying ? 'default' : 'primary'"
                    size="small"
                    @click="togglePlay"
                  >
                    <PauseCircleOutlined v-if="isPlaying" />
                    <PlayCircleOutlined v-else />
                    {{ isPlaying ? '暂停' : '播放' }}
                  </a-button>
                  <a-button size="small" @click="resetPlayback"> <ReloadOutlined /> 重置 </a-button>
                  <span class="convergence-frame-info">
                    迭代 {{ currentFrame }} / {{ totalFrames }}
                  </span>
                  <a-slider
                    v-model:value="currentFrame"
                    :min="0"
                    :max="totalFrames"
                    :step="1"
                    class="convergence-slider"
                    :tooltip="{ formatter: (v: number) => `迭代 ${v}` }"
                  />
                </div>

                <div ref="convergenceChartRef" class="convergence-chart" />
              </template>

              <!-- 粒子轨迹视图 (SeedTrajectory) -->
              <div
                v-if="convergenceTab === 'trajectory' && hasPopulationSnapshots"
                class="convergence-trajectory"
              >
                <SeedTrajectory
                  :convergence-data="convergenceData!"
                  :height="480"
                  :auto-play="convergenceExpanded"
                  :show-controls="true"
                  :trail-length="14"
                  default-view="2d"
                />
              </div>

              <!-- 元信息 -->
              <div class="convergence-meta" v-if="convergenceData?.metadata">
                <span>算法：{{ convergenceData.metadata.algorithm || 'AOO' }}</span>
                <span>种群大小：{{ convergenceData.metadata.populationSize }}</span>
                <span>精英数量：{{ convergenceData.metadata.eliteCount }}</span>
                <span>总耗时：{{ convergenceData.metadata.totalTimeSeconds?.toFixed(1) }}s</span>
                <span>收敛代数：{{ convergenceData.metadata.convergenceIteration }}</span>
              </div>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </div>

      <!-- 无收敛数据的说明 -->
      <div
        v-else-if="currentPath?.metadata?.generationTime"
        class="convergence-section convergence-section--empty"
      >
        <div class="convergence-empty">
          <BarChartOutlined style="font-size: 28px; color: #a8a6a2" />
          <span>当前路径不包含 AOO 收敛过程数据</span>
        </div>
      </div>
    </template>

    <!-- =========================================================
         重新规划：选择依据的诊断历史
         ========================================================= -->
    <a-modal
      v-model:visible="replanModalVisible"
      title="重新规划学习路径"
      :footer="null"
      :width="isMobile ? '90%' : 640"
      class="replan-modal"
    >
      <p class="replan-tip">
        请选择本次重新规划所依据的一次认知诊断结果，系统将根据该次诊断的薄弱知识点与掌握度重新优化路径。
      </p>
      <div class="replan-chat-switch">
        <a-switch v-model:checked="replanUseChat" :disabled="replanLoading" />
        <div class="rcs-text">
          <span class="rcs-title">叠加「智能问答对话分析」</span>
          <span class="rcs-desc">
            将所选诊断作为基底，并融合「对话画像」中梳理出的掌握特点（按动态权重 λ 叠加），生成更贴合近期对话情况的路径。
          </span>
        </div>
      </div>
      <div v-if="replanLoading" class="replan-loading">
        <a-spin tip="正在加载诊断历史..." />
      </div>
      <a-empty
        v-else-if="replanHistory.length === 0"
        description="暂无认知诊断记录，请先完成一次测评"
      />
      <a-list
        v-else
        class="replan-list"
        :data-source="replanHistory"
        item-layout="horizontal"
      >
        <template #renderItem="{ item }">
          <a-list-item class="replan-list-item" @click="confirmReplan(item)">
            <a-list-item-meta>
              <template #title>
                <span class="replan-item-title">
                  诊断于 {{ formatDate(item.created_at) }}
                </span>
              </template>
              <template #description>
                <span class="replan-item-desc">
                  综合得分 {{ item.score }} · 掌握度 {{ Math.round(item.mastery * 100) }}%
                  <template v-if="item.weak_points?.length">
                    · 薄弱：{{ item.weak_points.slice(0, 3).join('、') }}
                  </template>
                </span>
              </template>
            </a-list-item-meta>
            <template #actions>
              <a-button type="primary" ghost size="small">选用此次</a-button>
            </template>
          </a-list-item>
        </template>
      </a-list>
    </a-modal>

    <!-- =========================================================
         P2 待采纳版本：变更详情（diff 高亮）
         ========================================================= -->
    <a-modal
      v-model:visible="diffVisible"
      title="路径变更详情"
      :footer="null"
      :width="isMobile ? '90%' : 680"
      class="path-diff-modal"
    >
      <template v-if="pendingPath?.diff">
        <a-alert
          :message="pendingPath.diff.summary"
          type="info"
          show-icon
          class="diff-summary"
        />
        <div v-if="pendingPath.explanation" class="diff-explain">
          <div class="diff-explain-title">
            <BulbOutlined /> 为什么路径变了？
          </div>
          <p class="diff-explain-body">{{ pendingPath.explanation }}</p>
        </div>
        <div class="diff-section" v-if="pendingPath.diff.added.length">
          <div class="diff-section-title diff-added-title">
            <PlusCircleOutlined /> 新增 {{ pendingPath.diff.added.length }} 个
          </div>
          <div
            v-for="t in pendingPath.diff.added"
            class="diff-row diff-row--added"
          >
            <span class="diff-kp">{{ t.name || t.kp_id }}</span>
            <span class="diff-meta">第 {{ t.day }} 天 · {{ t.type }}</span>
          </div>
        </div>
        <div class="diff-section" v-if="pendingPath.diff.removed.length">
          <div class="diff-section-title diff-removed-title">
            <MinusCircleOutlined /> 移除 {{ pendingPath.diff.removed.length }} 个
          </div>
          <div
            v-for="t in pendingPath.diff.removed"
            class="diff-row diff-row--removed"
          >
            <span class="diff-kp">{{ t.name || t.kp_id }}</span>
            <span class="diff-meta">原第 {{ t.day }} 天</span>
          </div>
        </div>
        <div class="diff-section" v-if="pendingPath.diff.changed.length">
          <div class="diff-section-title diff-changed-title">
            <SwapOutlined /> 调整 {{ pendingPath.diff.changed.length }} 个
          </div>
          <div
            v-for="t in pendingPath.diff.changed"
            class="diff-row diff-row--changed"
          >
            <span class="diff-kp">{{ t.name || t.kp_id }}</span>
            <span class="diff-meta">
              <template v-if="t.day">
                第 {{ t.day.from }} 天 → 第 {{ t.day.to }} 天
              </template>
              <template v-if="t.type">
                · 类型 {{ t.type.from }} → {{ t.type.to }}
              </template>
            </span>
          </div>
        </div>
      </template>
      <a-empty v-else description="无对比基准（如首个版本）" />
      <div class="diff-footer">
        <a-button
          type="primary"
          :loading="adopting"
          @click="handleAdopt"
        >
          <CheckOutlined /> 一键采纳此版本
        </a-button>
      </div>
    </a-modal>
  </div>
</template>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

// ============================================================
//   页面容器
// ============================================================
.path-page {
  max-width: var(--content-max-width, clamp(60rem, 80rem, 80rem));
  margin: 0 auto;
  padding: 0 0 clamp(1.5rem, 2.5rem, 3rem);
}

// ============================================================
//   页面头部
// ============================================================
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: @spacing-lg;
  flex-wrap: wrap;
  gap: @spacing-sm;
}

.page-title {
  font-size: @font-size-2xl;
  font-weight: @font-weight-heavy;
  color: @gray-50;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-icon {
  color: @brand-oat-300;
  font-size: 26px;
}

.header-right {
  display: flex;
  gap: @spacing-sm;
  flex-wrap: wrap;
}

.action-btn {
  border-radius: @radius-btn;
  font-weight: @font-weight-medium;
  font-size: @font-size-sm;
  height: 34px;
  display: flex;
  align-items: center;
  gap: 4px;
}

// ============================================================
//   状态卡片
// ============================================================
.state-card {
  min-height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.generating-inner {
  text-align: center;

  .spin-icon {
    font-size: 48px;
    color: @brand-oat-300;
    margin-bottom: @spacing-md;
    opacity: 0.6;
  }

  h3 {
    font-size: @font-size-lg;
    color: @gray-50;
    margin: @spacing-md 0 @spacing-sm;
  }

  p {
    font-size: @font-size-sm;
    color: @gray-400;
    margin: 0 0 @spacing-lg;
  }
}

.generating-progress {
  max-width: 320px;
  margin: 0 auto;
}

// ============================================================
//   概览卡片网格 — 金属精密风格
// ============================================================
.overview-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr 1.3fr 1.3fr;
  grid-template-rows: auto auto;
  gap: @spacing-md;
  margin-bottom: @spacing-lg;
}

.overview-card {
  .metal-card();
  padding: 16px 18px;
  .metal-card-hover();
  position: relative;
  overflow: hidden;

  &::after {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    width: 32px;
    height: 24px;
    background: linear-gradient(135deg, transparent 40%, rgba(212, 163, 115, 0.06) 100%);
    pointer-events: none;
  }
}

// ── 信息卡片（跨整行） ──
.overview-card--info {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;

  &::after {
    display: none;
  }
}

.overview-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.overview-card-label {
  font-size: @font-size-xs;
  color: @gray-400;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.overview-card-title {
  font-size: @font-size-md;
  font-weight: @font-weight-bold;
  color: @gray-50;
}

.overview-card-meta {
  font-size: @font-size-xs;
  color: @gray-400;
  display: flex;
  gap: @spacing-md;
  font-family: @font-family-mono;
}

// ── 度量卡片 ──
.overview-card--metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.overview-card-icon {
  width: 36px;
  height: 36px;
  border-radius: @radius-btn;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.overview-metric-value {
  .spring-number();
  font-size: 28px;
  font-weight: @font-weight-heavy;
  color: @brand-oat-300;
  line-height: 1.1;
  font-family: @font-family-mono;
}

.metric-unit {
  font-size: 13px;
  font-weight: @font-weight-medium;
  color: @gray-400;
  margin-left: 2px;
}

.overview-metric-label {
  font-size: @font-size-xs;
  color: @gray-400;
  margin-top: 3px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

// ── 仪表盘卡片 ──
.overview-card--gauge {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.gauge-wrap {
  position: relative;
  width: 90px;
  height: 70px;
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 2px;
}

.gauge-svg {
  width: 100%;
  height: 55px;

  path:first-child {
    stroke: rgba(255, 255, 255, 0.06);
  }
}

.gauge-value-arc {
  transition: stroke-dasharray 1s ease;
}

.gauge-value {
  font-size: 18px;
  font-weight: @font-weight-heavy;
  line-height: 1;
  margin-top: -6px;
  font-family: @font-family-mono;
}

// ── 进度环卡片 ──
.overview-card--progress {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.progress-circle-wrap {
  position: relative;
  width: 68px;
  height: 68px;
  margin-bottom: 4px;
}

.progress-circle-svg {
  width: 100%;
  height: 100%;

  circle:first-child {
    stroke: rgba(255, 255, 255, 0.06);
  }
}

.progress-circle-arc {
  transition: stroke-dasharray 1.2s ease;
}

.progress-circle-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  line-height: 1;
}

.progress-circle-value {
  font-size: 18px;
  font-weight: @font-weight-heavy;
  color: @gray-50;
  font-family: @font-family-mono;
}

.progress-circle-unit {
  font-size: @font-size-xs;
  color: @gray-400;
}

// ── 扩展卡片（覆盖知识点 + 日均 + 得分） ──
.overview-card--extras {
  grid-column: 1 / -1;
  padding: 10px 20px;

  &::after {
    display: none;
  }
}

.extra-row {
  display: flex;
  align-items: center;
  justify-content: space-around;
}

.extra-item {
  text-align: center;
}

.extra-value {
  .spring-number();
  font-size: 22px;
  font-weight: @font-weight-bold;
  color: @gray-50;
  line-height: 1.2;
  font-family: @font-family-mono;
}

.extra-label {
  font-size: @font-size-xs;
  color: @gray-400;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.extra-divider {
  width: 1px;
  height: 32px;
  background: rgba(255, 255, 255, 0.08);
}

// ============================================================
//   路径切换 Tabs — 金属精密
// ============================================================
.variant-tabs {
  display: flex;
  gap: @spacing-sm;
  margin-bottom: @spacing-md;
  flex-wrap: wrap;
}

.variant-tab {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 18px;
  border: 1px solid @metal-border;
  border-radius: @radius-btn;
  background: @metal-bg;
  color: @gray-300;
  font-size: 13px;
  font-weight: @font-weight-medium;
  cursor: pointer;
  transition: all @transition-fast;
  position: relative;
  font-family: inherit;

  &:hover {
    border-color: @metal-border-hover;
    background: @metal-bg-hover;
    color: @gray-50;
  }

  &.is-active {
    border-color: @brand-oat-300;
    background: @metal-bg-active;
    color: @brand-oat-300;
    box-shadow: @shadow-oat-accent;
  }
}

.variant-tab-icon {
  font-size: 15px;
}

.variant-tag {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: @radius-tag;
  font-weight: @font-weight-bold;
  font-family: @font-family-mono;

  &.current {
    background: @brand-oat-300;
    color: @gray-900;
  }
}

// ============================================================
//   每日详情面板 — 精密紧凑
// ============================================================
.daily-detail {
  margin-top: @spacing-lg;
  .metal-card();
  overflow: hidden;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.daily-detail-header {
  display: flex;
  align-items: center;
  gap: @spacing-md;
  padding: 14px 18px;
  border-bottom: 1px solid @metal-border;
  background: rgba(255, 255, 255, 0.015);
}

.daily-detail-title-row {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  flex: 1;
}

.daily-nav-btn {
  width: 26px;
  height: 26px;
  border: 1px solid @metal-border;
  border-radius: @radius-btn;
  background: @metal-bg;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: @gray-300;
  font-size: 11px;
  transition: all @transition-fast;

  &:hover:not(:disabled) {
    border-color: @brand-oat-300;
    color: @brand-oat-300;
  }

  &:disabled {
    opacity: 0.2;
    cursor: not-allowed;
  }
}

.daily-detail-title {
  font-size: @font-size-md;
  font-weight: @font-weight-bold;
  color: @gray-50;
  margin: 0;
}

.daily-detail-meta {
  display: flex;
  gap: @spacing-md;
  font-size: @font-size-xs;
  color: @gray-400;
  font-family: @font-family-mono;

  span {
    display: flex;
    align-items: center;
    gap: 3px;
  }
}

.daily-task-list {
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: @spacing-sm;
  max-height: 440px;
  overflow-y: auto;
}

.daily-task-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  border-radius: @radius-card;
  border: 1px solid @metal-border;
  background: rgba(255, 255, 255, 0.015);
  transition: all @transition-fast;

  &:hover {
    border-color: rgba(255, 255, 255, 0.1);
    background: rgba(255, 255, 255, 0.03);
  }

  &.is-completed {
    background: rgba(46, 204, 113, 0.04);
    border-color: rgba(46, 204, 113, 0.1);

    .daily-task-name {
      text-decoration: line-through;
      color: @gray-400;
    }
  }
}

.daily-task-status {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  cursor: pointer;
  transition: all @transition-fast;
  color: transparent;
  font-size: 12px;
  margin-top: 2px;

  .is-completed & {
    color: @color-success;
  }
}

.daily-task-body {
  flex: 1;
  min-width: 0;
}

.daily-task-header {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  margin-bottom: 3px;
}

.daily-task-name {
  font-size: @font-size-md;
  font-weight: @font-weight-semibold;
  color: @gray-50;
}

.daily-task-type {
  font-size: @font-size-xs;
  padding: 1px 7px;
  border-radius: @radius-tag;
  font-weight: @font-weight-medium;
  white-space: nowrap;
}

.daily-task-desc {
  font-size: @font-size-sm;
  color: @gray-400;
  margin: 0 0 6px 0;
  line-height: @line-height-base;
}

.daily-task-footer {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  font-size: @font-size-xs;
}

.daily-task-kp {
  color: @brand-oat-300;
  background: rgba(212, 163, 115, 0.08);
  padding: 1px 7px;
  border-radius: @radius-tag;
  font-weight: @font-weight-medium;
  font-family: @font-family-mono;
}

.daily-task-time {
  color: @gray-400;
  display: flex;
  align-items: center;
  gap: 3px;
}

.daily-task-resources {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.resource-link {
  font-size: @font-size-xs;
  color: @brand-cyan-400;
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 8px;
  background: rgba(0, 212, 255, 0.06);
  border-radius: @radius-tag;
  transition: background @transition-fast;

  &:hover {
    background: rgba(0, 212, 255, 0.12);
  }
}

.daily-task-action {
  flex-shrink: 0;
  margin-top: 2px;
  border-radius: @radius-btn;
  font-weight: @font-weight-medium;
  font-size: @font-size-xs;
}

// ============================================================
//   AOO 收敛回放 — 精密控制面板
// ============================================================
.convergence-section {
  margin-top: @spacing-lg;
  border-radius: @radius-card;
  overflow: hidden;
  .metal-card();

  :deep(.ant-collapse) {
    border: none;
    background: transparent;
  }

  :deep(.ant-collapse-item) {
    border: none;
  }

  :deep(.ant-collapse-header) {
    padding: 14px 18px;
    font-weight: @font-weight-semibold;
    color: @gray-50;
    font-size: @font-size-md;
  }

  :deep(.ant-collapse-content-box) {
    padding: 0 18px 18px;
  }
}

.convergence-section--empty {
  padding: 0;
  border: 1px dashed @metal-border;
}

.convergence-empty {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  padding: 20px 18px;
  color: @gray-400;
  font-size: @font-size-sm;
}

.convergence-header {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
}

.convergence-header-icon {
  color: @brand-blue-400;
  font-size: 17px;
}

.convergence-header-badge {
  font-size: @font-size-xs;
  color: @gray-400;
  margin-left: auto;
  font-weight: @font-weight-normal;
  font-family: @font-family-mono;
}

.convergence-body {
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
}

/* ---- 收敛视图 Tab 切换 ---- */
.convergence-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 10px;
  align-self: flex-start;
}

.convergence-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #94a3b8;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 200ms ease;
}

.convergence-tab:hover {
  color: #f8fafc;
  background: rgba(255, 255, 255, 0.04);
}

.convergence-tab--active {
  color: #d4a373;
  background: rgba(212, 163, 115, 0.12);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

.convergence-trajectory {
  /* SeedTrajectory 组件的深色背景容器已内置于组件，此处仅做留白 */
}

.convergence-controls {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
}

.convergence-frame-info {
  font-size: @font-size-xs;
  color: @gray-400;
  white-space: nowrap;
  font-family: @font-family-mono;
}

.convergence-slider {
  flex: 1;
  min-width: 100px;
}

.convergence-chart {
  width: 100%;
  aspect-ratio: 16 / 10;
  min-height: 240px;
}

.convergence-meta {
  display: flex;
  flex-wrap: wrap;
  gap: @spacing-sm;
  font-size: @font-size-xs;
  color: @gray-400;

  span {
    background: rgba(255, 255, 255, 0.04);
    padding: 2px 8px;
    border-radius: @radius-tag;
    color: @gray-300;
    font-family: @font-family-mono;
  }
}

// ============================================================
//   响应式
// ============================================================
@media (max-width: 1280px) {
  .path-page {
    max-width: 100%;
    padding: 0 @spacing-md 2rem;
  }
}

@media (max-width: 1024px) {
  .overview-grid {
    grid-template-columns: 1fr 1fr 1fr;
    grid-template-rows: auto;
  }

  .overview-card--info {
    grid-column: 1 / -1;
  }
  .overview-card--extras {
    grid-column: 1 / -1;
  }

  .convergence-chart {
    aspect-ratio: 4 / 3;
    min-height: 260px;
  }
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: @spacing-sm;
  }

  .header-right {
    width: 100%;
    justify-content: flex-start;
  }

  .overview-grid {
    grid-template-columns: 1fr 1fr;
  }

  .overview-card--info {
    grid-column: 1 / -1;
  }
  .overview-card--gauge {
    grid-column: 1 / -1;
  }
  .overview-card--progress {
    grid-column: 1 / -1;
  }
  .overview-card--extras {
    grid-column: 1 / -1;
  }

  .overview-card--info {
    flex-direction: column;
    align-items: flex-start;
    gap: @spacing-sm;
  }

  .daily-detail-header {
    flex-wrap: wrap;
  }

  .daily-detail-meta {
    width: 100%;
    justify-content: flex-start;
  }

  .convergence-controls {
    flex-wrap: wrap;
  }

  .convergence-slider {
    min-width: 100%;
    order: 10;
  }

  .variant-tab {
    padding: 0.375rem 0.75rem;
    font-size: @font-size-xs;
    min-height: @touch-target-min;
  }

  .daily-task-action {
    font-size: @font-size-xs;
    padding: 0 10px;
    min-height: @touch-target-min;
  }

  .convergence-chart {
    aspect-ratio: 4 / 3;
    min-height: 240px;
  }

  .task-tooltip {
    left: auto;
    right: 0;
    width: 240px;
  }
}

@media (max-width: 480px) {
  .path-page {
    padding: 0 @spacing-xs 1.5rem;
  }

  .page-header {
    flex-direction: column;
    gap: @spacing-sm;
  }

  .overview-grid {
    grid-template-columns: 1fr;
  }

  .overview-card--info,
  .overview-card--gauge,
  .overview-card--progress,
  .overview-card--extras,
  .overview-card--metric {
    grid-column: 1 / -1;
  }

  .variant-tab {
    padding: 0.3125rem 0.5rem;
    font-size: @font-size-xs;
  }

  .convergence-chart {
    aspect-ratio: 1 / 1;
    min-height: 220px;
  }
}

// ============================================================
//   P2 待采纳重规划版本横幅
// ============================================================
.pending-banner {
  display: flex;
  align-items: center;
  gap: @spacing-md;
  margin-bottom: @spacing-lg;
  padding: @spacing-md @spacing-lg;
  border-radius: 12px;
  background: linear-gradient(90deg, rgba(212, 163, 115, 0.12), rgba(74, 108, 247, 0.08));
  border: 1px solid rgba(212, 163, 115, 0.35);

  .pending-icon {
    font-size: 22px;
    color: @brand-oat-300;
    flex-shrink: 0;
  }

  .pending-body {
    flex: 1;
    min-width: 0;
  }

  .pending-title {
    font-size: @font-size-base;
    font-weight: 600;
    color: @gray-50;
    display: flex;
    align-items: center;
    gap: @spacing-xs;

    .pending-tag {
      margin: 0;
    }
  }

  .pending-desc {
    font-size: 12.5px;
    color: @gray-300;
    margin-top: 2px;

    .pending-meta {
      color: @gray-400;
      margin-left: 4px;
    }
  }

  .pending-explanation {
    margin-top: @spacing-xs;
    font-size: 12px;
    line-height: 1.6;
    color: @gray-200;
    background: rgba(74, 108, 247, 0.10);
    border-left: 2px solid @brand-blue-400;
    border-radius: 4px;
    padding: 6px 10px;
    display: flex;
    gap: 6px;

    .explain-icon {
      color: @brand-blue-400;
      flex-shrink: 0;
      margin-top: 2px;
    }
  }

  .pending-actions {
    display: flex;
    gap: @spacing-sm;
    flex-shrink: 0;
  }
}

// ============================================================
//   P2 路径变更详情（diff 高亮）
// ============================================================
.path-diff-modal {
  .diff-summary {
    margin-bottom: @spacing-md;
  }

  .diff-explain {
    margin-bottom: @spacing-md;
    padding: @spacing-md;
    border-radius: 10px;
    background: linear-gradient(135deg, rgba(74, 108, 247, 0.12), rgba(0, 212, 255, 0.06));
    border: 1px solid rgba(74, 108, 247, 0.3);

    .diff-explain-title {
      font-size: @font-size-sm;
      font-weight: 600;
      color: @brand-blue-400;
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 6px;
    }

    .diff-explain-body {
      margin: 0;
      font-size: 12.5px;
      line-height: 1.7;
      color: @gray-200;
      white-space: pre-wrap;
    }
  }

  .diff-section {
    margin-bottom: @spacing-md;

    .diff-section-title {
      font-size: @font-size-sm;
      font-weight: 600;
      margin-bottom: @spacing-xs;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .diff-added-title {
      color: #4ade80;
    }

    .diff-removed-title {
      color: #f87171;
    }

    .diff-changed-title {
      color: @brand-oat-300;
    }

    .diff-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 6px 10px;
      border-radius: 8px;
      margin-bottom: 4px;
      font-size: 12.5px;

      .diff-kp {
        color: @gray-50;
        font-weight: 500;
      }

      .diff-meta {
        color: @gray-300;
        font-size: 12px;
      }
    }

    .diff-row--added {
      background: rgba(74, 222, 128, 0.10);
      border-left: 3px solid #4ade80;
    }

    .diff-row--removed {
      background: rgba(248, 113, 113, 0.10);
      border-left: 3px solid #f87171;
      text-decoration: line-through;
      opacity: 0.8;
    }

    .diff-row--changed {
      background: rgba(212, 163, 115, 0.10);
      border-left: 3px solid @brand-oat-300;
    }
  }

  .diff-footer {
    text-align: right;
    margin-top: @spacing-md;
  }
}
</style>

<!-- 重新规划对话框（a-modal teleport 到 body，需非 scoped 样式） -->
<style lang="less">
.replan-modal {
  .ant-modal-header {
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
  .ant-modal-title {
    color: #f1f5f9;
    font-weight: 600;
  }
  .ant-modal-content {
    background: #141b2b;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 14px;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.45);
  }
  .ant-modal-close-x {
    color: #94a3b8;
  }
  .ant-modal-body {
    padding-top: 12px;
  }
}
.replan-tip {
  color: #94a3b8;
  font-size: 13px;
  line-height: 1.6;
  margin: 0 0 16px;
}
.replan-chat-switch {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  margin-bottom: 16px;
  background: rgba(74, 108, 247, 0.08);
  border: 1px solid rgba(74, 108, 247, 0.25);
  border-radius: 10px;

  .rcs-text {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .rcs-title {
    font-size: 13px;
    font-weight: 600;
    color: #cbd5e1;
  }
  .rcs-desc {
    font-size: 12px;
    color: #64748b;
    line-height: 1.55;
  }
}
.replan-loading {
  display: flex;
  justify-content: center;
  padding: 32px 0;
}
.replan-list {
  max-height: 52vh;
  overflow-y: auto;
  .ant-list-item {
    cursor: pointer;
    border-radius: 10px;
    padding: 12px 14px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    transition: all 0.18s ease;
    &:hover {
      border-color: rgba(212, 163, 115, 0.5);
      background: rgba(212, 163, 115, 0.06);
    }
  }
  .ant-list-item-meta-title {
    margin-bottom: 4px;
  }
}
.replan-item-title {
  color: #e2e8f0;
  font-weight: 600;
}
.replan-item-desc {
  color: #94a3b8;
  font-size: 12.5px;
}
</style>
