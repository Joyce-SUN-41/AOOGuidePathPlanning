<script setup lang="ts">
/**
 * 教师仪表盘 — 班级学情总览（仅供教师角色访问）
 *
 * 六大功能区域：
 *   1. 班级概览卡片(4) — 总学生数 / 平均掌握度 / 平均认知负荷 / 路径完成率
 *   2. 学生列表(a-table) + 认知负荷分布图(ECharts bar)
 *   3. 共性薄弱知识点 Top 5
 *   4. 全班掌握度趋势图(ECharts line)
 *   5. 预警通知(需要关注的学生)
 *   6. 学生详情抽屉(点击行查看)
 */
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { useUserStore } from '@/stores/user'
import { teacherApi } from '@/api/modules/teacher'
import type {
  ClassOverview,
  StudentSummary,
  WeakKpStat,
  MasteryTrendPoint,
  AlertStudent,
  StudentDetail
} from '@/types'
import {
  TeamOutlined,
  ThunderboltOutlined,
  AimOutlined,
  ReloadOutlined,
  WarningOutlined,
  TrophyOutlined,
  BarChartOutlined,
  LineChartOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  UserOutlined
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

// ============================================================
//   Store & Router
// ============================================================
const router = useRouter()
const userStore = useUserStore()

// 角色守卫：非教师重定向首页（作为路由守卫的补充）
if (!userStore.isTeacher) {
  router.replace({ path: '/home' })
}

// ============================================================
//   State
// ============================================================
const loading = ref(true)
const tableLoading = ref(false)

// 概览
const overview = ref<ClassOverview>(getFallbackOverview())

// 学生列表
const students = ref<StudentSummary[]>([])
const studentsSortField = ref<string>('avgMastery')
const studentsSortOrder = ref<'asc' | 'desc'>('desc')

// 薄弱知识点
const weakKps = ref<WeakKpStat[]>([])

// 掌握度趋势
const masteryTrend = ref<MasteryTrendPoint[]>([])

// 预警学生
const alerts = ref<AlertStudent[]>([])

// 学生详情抽屉
const detailDrawerVisible = ref(false)
const detailLoading = ref(false)
const selectedStudent = ref<StudentSummary | null>(null)
const studentDetail = ref<StudentDetail | null>(null)

// ECharts
const chartRefs = {
  loadDist: ref<HTMLDivElement | null>(null),
  trend: ref<HTMLDivElement | null>(null)
}
const chartInstances: Record<string, echarts.ECharts | null> = {
  loadDist: null,
  trend: null
}
const resizeObservers: ResizeObserver[] = []

// ============================================================
//   表头配置
// ============================================================
const studentColumns = [
  {
    title: '姓名',
    dataIndex: 'nickname',
    key: 'nickname',
    width: 100,
    sorter: true,
    customRender: ({ record }: { record: StudentSummary }) =>
      h('span', { class: 'student-name-cell' }, [
        h('span', { class: 'student-avatar-dot' }),
        record.nickname || record.name
      ])
  },
  {
    title: '平均掌握度',
    dataIndex: 'avgMastery',
    key: 'avgMastery',
    width: 140,
    sorter: true,
    customRender: ({ text }: { text: number }) => {
      const pct = Math.round(text * 100)
      const color =
        pct >= 80 ? '#52C41A' : pct >= 60 ? '#4F7CFF' : pct >= 40 ? '#FA8C16' : '#FF4D4F'
      return h('div', { class: 'mastery-cell' }, [
        h(
          'div',
          { class: 'mastery-bar-bg' },
          h('div', { class: 'mastery-bar-fill', style: { width: pct + '%', background: color } })
        ),
        h('span', { class: 'mastery-pct', style: { color } }, pct + '%')
      ])
    }
  },
  {
    title: '认知负荷',
    dataIndex: 'cognitiveLoad',
    key: 'cognitiveLoad',
    width: 120,
    sorter: true,
    customRender: ({ text }: { text: number }) => {
      const pct = Math.round(text * 100)
      const color = pct > 70 ? '#FF4D4F' : pct > 50 ? '#FA8C16' : '#52C41A'
      const label = pct > 70 ? '偏高' : pct > 50 ? '适中' : '良好'
      return h(
        'span',
        {
          class: 'load-tag',
          style: { color, background: color + '15', borderColor: color + '30' }
        },
        label
      )
    }
  },
  {
    title: '路径完成度',
    dataIndex: 'pathCompletion',
    key: 'pathCompletion',
    width: 130,
    sorter: true,
    customRender: ({ text }: { text: number }) =>
      h('div', { class: 'completion-cell' }, [
        h('a-progress', {
          percent: text,
          size: 'small',
          strokeColor: text >= 80 ? '#52C41A' : '#4F7CFF',
          'show-info': false,
          style: { width: '70px' }
        }),
        h('span', { class: 'completion-pct' }, Math.round(text) + '%')
      ])
  },
  {
    title: '最近活跃',
    dataIndex: 'lastActiveDate',
    key: 'lastActiveDate',
    width: 110,
    sorter: true
  },
  {
    title: '操作',
    key: 'action',
    width: 80,
    fixed: 'right' as const,
    customRender: ({ record }: { record: StudentSummary }) =>
      h('a', { class: 'action-link', onClick: () => openStudentDetail(record) }, '查看详情')
  }
]

// ============================================================
//   Computed
// ============================================================
const loadDistData = computed(() => {
  return students.value.map((s) => ({
    name: s.nickname || s.name,
    value: Math.round(s.cognitiveLoad * 100),
    color: s.cognitiveLoad > 0.7 ? '#FF4D4F' : s.cognitiveLoad > 0.5 ? '#FA8C16' : '#4F7CFF'
  }))
})

const highLoadStudents = computed(() => students.value.filter((s) => s.cognitiveLoad > 0.7))

const alertCount = computed(() => alerts.value.length)
const weakKpsTop5 = computed(() => weakKps.value.slice(0, 5))

// ============================================================
//   导入 h 函数（用于表格 customRender）
// ============================================================
import { h } from 'vue'

// ============================================================
//   初始化 & 数据加载
// ============================================================
async function loadAllData() {
  loading.value = true
  await Promise.allSettled([
    loadOverview(),
    loadStudents(),
    loadWeakKps(),
    loadMasteryTrend(),
    loadAlerts()
  ])
  loading.value = false
  await nextTick()
  initAllCharts()
}

async function loadOverview() {
  try {
    overview.value = await teacherApi.getClassOverview()
  } catch {
    overview.value = getFallbackOverview()
  }
}

async function loadStudents() {
  tableLoading.value = true
  try {
    students.value = await teacherApi.getStudents({
      sortBy: studentsSortField.value,
      order: studentsSortOrder.value
    })
  } catch {
    students.value = getFallbackStudents()
  }
  tableLoading.value = false
}

async function loadWeakKps() {
  try {
    weakKps.value = await teacherApi.getWeakKps(5)
  } catch {
    weakKps.value = getFallbackWeakKps()
  }
}

async function loadMasteryTrend() {
  try {
    masteryTrend.value = await teacherApi.getMasteryTrend(30)
  } catch {
    masteryTrend.value = getFallbackTrend()
  }
}

async function loadAlerts() {
  try {
    alerts.value = await teacherApi.getAlerts()
  } catch {
    alerts.value = getFallbackAlerts()
  }
}

// ============================================================
//   学生详情
// ============================================================
async function openStudentDetail(student: StudentSummary) {
  selectedStudent.value = student
  detailDrawerVisible.value = true
  detailLoading.value = true
  try {
    studentDetail.value = await teacherApi.getStudentDetail(student.id)
  } catch {
    studentDetail.value = getFallbackStudentDetail(student)
  }
  detailLoading.value = false
}

function closeDetail() {
  detailDrawerVisible.value = false
  selectedStudent.value = null
  studentDetail.value = null
}

// ============================================================
//   表格排序
// ============================================================
function handleTableChange(_pagination: unknown, _filters: unknown, sorter: any) {
  if (sorter.field) {
    studentsSortField.value = sorter.field
    studentsSortOrder.value = sorter.order === 'ascend' ? 'asc' : 'desc'
    loadStudents()
  }
}

// ============================================================
//   ECharts：认知负荷分布柱状图
// ============================================================
function initLoadDistChart() {
  const el = chartRefs.loadDist.value
  if (!el) return

  if (chartInstances['loadDist']) chartInstances['loadDist']!.dispose()
  const chart = echarts.init(el)
  chartInstances['loadDist'] = chart

  const dataItems = loadDistData.value

  chart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: any) => {
        const item = params[0]
        const color = item.data?.color || '#4F7CFF'
        return `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${color};margin-right:6px;"></span>
          <b>${item.name}</b><br/>
          认知负荷：<b style="color:${color}">${item.value}%</b>
          ${item.value > 70 ? '<br/><span style="color:#FF4D4F">⚠ 超过警戒线</span>' : ''}`
      }
    },
    grid: { top: 20, right: 20, bottom: 50, left: 50 },
    xAxis: {
      type: 'category',
      data: dataItems.map((d) => d.name),
      axisLabel: { rotate: 30, fontSize: 11, color: '#8c8c8c' },
      axisTick: { alignWithLabel: true }
    },
    yAxis: {
      type: 'value',
      name: '%',
      min: 0,
      max: 100,
      axisLabel: { fontSize: 11, color: '#8c8c8c' },
      splitLine: { lineStyle: { color: '#f0f0f0', type: 'dashed' } }
    },
    series: [
      {
        type: 'bar',
        data: dataItems.map((d) => ({
          value: d.value,
          itemStyle: {
            color: d.color,
            borderRadius: [6, 6, 0, 0],
            shadowBlur: 4,
            shadowColor: d.color + '40',
            shadowOffsetY: 2
          }
        })),
        barWidth: Math.max(20, Math.min(36, 280 / dataItems.length)),
        emphasis: {
          itemStyle: { shadowBlur: 12, shadowOffsetY: 4 }
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#FF4D4F', type: 'dashed', width: 2 },
          label: {
            formatter: '警戒线 70%',
            position: 'end',
            fontSize: 11,
            color: '#FF4D4F',
            fontWeight: 600
          },
          data: [{ yAxis: 70 }]
        }
      }
    ]
  })

  bindResize(chart, el)
}

// ============================================================
//   ECharts：全班掌握度趋势图
// ============================================================
function initTrendChart() {
  const el = chartRefs.trend.value
  if (!el) return

  if (chartInstances['trend']) chartInstances['trend']!.dispose()
  const chart = echarts.init(el)
  chartInstances['trend'] = chart

  const dates = masteryTrend.value.map((d) => d.date.slice(5))
  const values = masteryTrend.value.map((d) => Math.round(d.avgMastery * 100))
  const counts = masteryTrend.value.map((d) => d.diagnosisCount)

  chart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const item = params[0]
        const idx = item.dataIndex
        return `<b>${masteryTrend.value[idx]?.date ?? ''}</b><br/>
          平均掌握度：<b style="color:#4F7CFF">${item.value}%</b><br/>
          参与诊断人数：${counts[idx]}人`
      }
    },
    grid: { top: 20, right: 20, bottom: 40, left: 55 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        fontSize: 10,
        color: '#8c8c8c',
        interval: Math.max(0, Math.floor(dates.length / 8) - 1)
      },
      axisLine: { lineStyle: { color: '#e8e8e8' } }
    },
    yAxis: {
      type: 'value',
      name: '%',
      min: 0,
      max: 100,
      axisLabel: { fontSize: 11, color: '#8c8c8c' },
      splitLine: { lineStyle: { color: '#f0f0f0', type: 'dashed' } }
    },
    series: [
      {
        type: 'line',
        data: values,
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: { color: '#4F7CFF', width: 3 },
        itemStyle: {
          color: '#4F7CFF',
          borderColor: '#fff',
          borderWidth: 2
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(79,124,255,0.20)' },
            { offset: 1, color: 'rgba(79,124,255,0.02)' }
          ])
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#FFD700', type: 'dashed', width: 2 },
          label: {
            formatter: '目标 80%',
            fontSize: 11,
            color: '#D4A017',
            fontWeight: 600
          },
          data: [{ yAxis: 80 }]
        }
      }
    ]
  })

  bindResize(chart, el)
}

function initAllCharts() {
  setTimeout(() => {
    initLoadDistChart()
    initTrendChart()
  }, 100)
}

function bindResize(chart: echarts.ECharts, el: HTMLElement) {
  const observer = new ResizeObserver(() => chart.resize())
  observer.observe(el)
  resizeObservers.push(observer)
}

function disposeAllCharts() {
  Object.values(chartInstances).forEach((c) => c?.dispose())
  resizeObservers.forEach((o) => o.disconnect())
  resizeObservers.length = 0
}

// ============================================================
//   页面刷新
// ============================================================
async function refresh() {
  await loadAllData()
  message.success('数据已刷新')
}

// ============================================================
//   格式化
// ============================================================
function formatPct(v: number): string {
  return Math.round(v * 100) + '%'
}
function formatLoadLabel(v: number): string {
  const p = Math.round(v * 100)
  if (p > 70) return '偏高⚠'
  if (p > 50) return '适中'
  return '良好'
}

// ============================================================
//   Fallback 数据（API 不可用时用模拟数据展示页面效果）
// ============================================================
function getFallbackOverview(): ClassOverview {
  return {
    totalStudents: 42,
    avgMastery: 0.68,
    avgCognitiveLoad: 0.52,
    avgPathCompletion: 61,
    highLoadCount: 7,
    lowMasteryCount: 12
  }
}

function getFallbackStudents(): StudentSummary[] {
  const names = [
    { name: 'zhangsan', nickname: '张三' },
    { name: 'lisi', nickname: '李四' },
    { name: 'wangwu', nickname: '王五' },
    { name: 'zhaoliu', nickname: '赵六' },
    { name: 'sunqi', nickname: '孙七' },
    { name: 'zhouba', nickname: '周八' },
    { name: 'wujiu', nickname: '吴九' },
    { name: 'zhengshi', nickname: '郑十' },
    { name: 'qianyue', nickname: '钱月' },
    { name: 'chenxing', nickname: '陈星' },
    { name: 'liuyu', nickname: '刘雨' },
    { name: 'huangshan', nickname: '黄山' },
    { name: 'linhai', nickname: '林海' },
    { name: 'maxue', nickname: '马雪' },
    { name: 'yanglei', nickname: '杨磊' }
  ]
  return names.map((n, i) => ({
    id: String(i + 1),
    name: n.name,
    nickname: n.nickname,
    avgMastery: 0.3 + Math.random() * 0.65,
    cognitiveLoad: 0.25 + Math.random() * 0.65,
    pathCompletion: Math.round((0.2 + Math.random() * 0.75) * 100),
    lastActiveDate: getRandomDate(14),
    completedTasks: Math.floor(4 + Math.random() * 30),
    totalTasks: 36,
    weakPointCount: Math.floor(1 + Math.random() * 6),
    subject: '数学',
    overallScore: Math.floor(30 + Math.random() * 65)
  }))
}

function getFallbackWeakKps(): WeakKpStat[] {
  return [
    { knowledgePoint: '梯度下降算法', studentCount: 18, avgMastery: 0.38 },
    { knowledgePoint: '神经网络基础', studentCount: 15, avgMastery: 0.42 },
    { knowledgePoint: '损失函数设计', studentCount: 14, avgMastery: 0.35 },
    { knowledgePoint: '反向传播原理', studentCount: 12, avgMastery: 0.45 },
    { knowledgePoint: '激活函数选择', studentCount: 10, avgMastery: 0.48 }
  ]
}

function getFallbackTrend(): MasteryTrendPoint[] {
  const dates: MasteryTrendPoint[] = []
  const now = new Date()
  let base = 0.48
  for (let i = 29; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 24 * 3600 * 1000)
    base += (Math.random() - 0.35) * 0.025
    base = Math.max(0.3, Math.min(0.85, base))
    dates.push({
      date: d.toISOString().slice(0, 10),
      avgMastery: base,
      diagnosisCount: Math.floor(5 + Math.random() * 20)
    })
  }
  return dates
}

function getFallbackAlerts(): AlertStudent[] {
  return [
    {
      studentId: '1',
      name: 'zhangsan',
      nickname: '张三',
      avgMastery: 0.32,
      cognitiveLoad: 0.82,
      reason: 'both',
      severity: 'danger'
    },
    {
      studentId: '3',
      name: 'wangwu',
      nickname: '王五',
      avgMastery: 0.41,
      cognitiveLoad: 0.76,
      reason: 'both',
      severity: 'danger'
    },
    {
      studentId: '9',
      name: 'qianyue',
      nickname: '钱月',
      avgMastery: 0.55,
      cognitiveLoad: 0.79,
      reason: 'highLoad',
      severity: 'warning'
    },
    {
      studentId: '12',
      name: 'huangshan',
      nickname: '黄山',
      avgMastery: 0.28,
      cognitiveLoad: 0.45,
      reason: 'lowMastery',
      severity: 'warning'
    },
    {
      studentId: '4',
      name: 'zhaoliu',
      nickname: '赵六',
      avgMastery: 0.36,
      cognitiveLoad: 0.71,
      reason: 'both',
      severity: 'danger'
    },
    {
      studentId: '14',
      name: 'maxue',
      nickname: '马雪',
      avgMastery: 0.35,
      cognitiveLoad: 0.68,
      reason: 'lowMastery',
      severity: 'warning'
    }
  ]
}

function getFallbackStudentDetail(student: StudentSummary): StudentDetail {
  return {
    summary: student,
    overallScore: student.overallScore ?? Math.round(student.avgMastery * 100),
    subject: student.subject ?? '数学',
    masteryLevels: [
      { knowledgePoint: '梯度下降算法', mastery: 0.35, level: 'weak', confidence: 0.72 },
      { knowledgePoint: '神经网络基础', mastery: 0.48, level: 'weak', confidence: 0.68 },
      { knowledgePoint: '损失函数设计', mastery: 0.62, level: 'developing', confidence: 0.81 },
      { knowledgePoint: '反向传播原理', mastery: 0.55, level: 'developing', confidence: 0.75 },
      { knowledgePoint: '激活函数选择', mastery: 0.78, level: 'proficient', confidence: 0.88 },
      { knowledgePoint: '优化器对比', mastery: 0.85, level: 'excellent', confidence: 0.92 }
    ],
    cognitiveLoad: {
      memoryLoad: 0.62 + Math.random() * 0.2,
      attentionLoad: 0.45 + Math.random() * 0.3,
      processingLoad: 0.55 + Math.random() * 0.25,
      overall: student.cognitiveLoad
    },
    weakPoints: [
      {
        knowledgePoint: '梯度下降算法',
        reason: '对学习率调整机制理解不足',
        severity: 'severe',
        suggestedRemediation: '建议通过可视化工具直观理解梯度下降过程'
      },
      {
        knowledgePoint: '神经网络基础',
        reason: '对层间连接和权重概念模糊',
        severity: 'moderate',
        suggestedRemediation: '推荐观看3Blue1Brown神经网络系列视频'
      },
      {
        knowledgePoint: '损失函数设计',
        reason: '未能区分不同损失函数的适用场景',
        severity: 'mild',
        suggestedRemediation: '练习题：为不同任务选择合适的损失函数'
      }
    ]
  }
}

function getRandomDate(daysBack: number): string {
  const d = new Date(Date.now() - Math.floor(Math.random() * daysBack * 86400000))
  return d.toISOString().slice(0, 10)
}

// ============================================================
//   认知负荷三维度颜色映射
// ============================================================
const loadColorMap: Record<string, string> = {
  memoryLoad: '#FA8C16',
  attentionLoad: '#722ED1',
  processingLoad: '#52C41A'
}

const loadLabelMap: Record<string, string> = {
  memoryLoad: '记忆负荷',
  attentionLoad: '注意力负荷',
  processingLoad: '加工负荷'
}

// ============================================================
//   认知负荷三维度计算
// ============================================================
function ratingFromLoad(val: number): '低' | '中' | '高' {
  if (val < 0.4) return '低'
  if (val < 0.7) return '中'
  return '高'
}

function ratingColorFromLoad(val: number): string {
  if (val < 0.4) return '#52C41A'
  if (val < 0.7) return '#FA8C16'
  return '#FF4D4F'
}

// ============================================================
//   生命周期
// ============================================================
onMounted(async () => {
  await loadAllData()
})

onUnmounted(() => {
  disposeAllCharts()
})
</script>

<template>
  <div class="teacher-dashboard">
    <!-- =============================================================== -->
    <!-- 1. 页面头部 + 班级概览卡片                                          -->
    <!-- =============================================================== -->
    <header class="dashboard-header">
      <div class="header-left">
        <TeamOutlined class="header-icon" />
        <div>
          <h1 class="header-title">教师仪表盘</h1>
          <p class="header-subtitle">班级学情数据总览，实时掌握每位学生的学习动态</p>
        </div>
      </div>
      <a-button :loading="loading" @click="refresh">
        <template #icon><ReloadOutlined /></template>
        刷新数据
      </a-button>
    </header>

    <!-- 概览卡片 -->
    <section class="overview-cards">
      <div class="stat-card">
        <div class="stat-icon students-icon"><TeamOutlined /></div>
        <div class="stat-body">
          <span class="stat-label">总学生数</span>
          <span class="stat-value">{{ overview.totalStudents }}</span>
          <span class="stat-sub">人</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon mastery-icon"><TrophyOutlined /></div>
        <div class="stat-body">
          <span class="stat-label">平均掌握度</span>
          <span class="stat-value">{{ formatPct(overview.avgMastery) }}</span>
          <span class="stat-sub">
            <a-tag
              :color="
                overview.avgMastery >= 0.7
                  ? 'green'
                  : overview.avgMastery >= 0.5
                    ? 'blue'
                    : 'orange'
              "
              size="small"
            >
              {{
                overview.avgMastery >= 0.7 ? '良好' : overview.avgMastery >= 0.5 ? '中等' : '需提升'
              }}
            </a-tag>
          </span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon load-icon"><ThunderboltOutlined /></div>
        <div class="stat-body">
          <span class="stat-label">平均认知负荷</span>
          <span class="stat-value">{{ formatPct(overview.avgCognitiveLoad) }}</span>
          <span class="stat-sub">
            <a-tag
              :color="
                overview.avgCognitiveLoad > 0.7
                  ? 'red'
                  : overview.avgCognitiveLoad > 0.5
                    ? 'orange'
                    : 'green'
              "
              size="small"
            >
              {{ formatLoadLabel(overview.avgCognitiveLoad) }}
            </a-tag>
            <span class="load-detail">高负荷 {{ overview.highLoadCount }}人</span>
          </span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon completion-icon"><AimOutlined /></div>
        <div class="stat-body">
          <span class="stat-label">路径完成率</span>
          <span class="stat-value">{{ Math.round(overview.avgPathCompletion) }}%</span>
          <span class="stat-sub">平均进度</span>
        </div>
      </div>
    </section>

    <!-- =============================================================== -->
    <!-- 2. 学生列表 + 认知负荷分布图                                        -->
    <!-- =============================================================== -->
    <section class="content-row two-col">
      <!-- 学生列表 -->
      <div class="glass-card student-table-card">
        <div class="card-header">
          <h3 class="card-title">
            <UserOutlined style="margin-right: 6px; color: #4f7cff" />
            学生列表
          </h3>
          <span class="card-count">共 {{ students.length }} 人</span>
        </div>
        <a-table
          :dataSource="students"
          :columns="studentColumns"
          :loading="tableLoading"
          :pagination="{
            pageSize: 10,
            showSizeChanger: true,
            pageSizeOptions: ['8', '10', '15', '20'],
            showTotal: (total: number) => `共 ${total} 人`
          }"
          :scroll="{ x: 700 }"
          rowKey="id"
          size="middle"
          :customRow="
            (record: StudentSummary) => ({
              style: { cursor: 'pointer' },
              onClick: () => openStudentDetail(record)
            })
          "
          @change="handleTableChange"
          class="student-table"
        />
      </div>

      <!-- 认知负荷分布图 -->
      <div class="glass-card chart-card">
        <div class="card-header">
          <h3 class="card-title">
            <BarChartOutlined style="margin-right: 6px; color: #fa8c16" />
            认知负荷分布
          </h3>
          <a-tag v-if="highLoadStudents.length > 0" color="red" size="small">
            {{ highLoadStudents.length }}人偏高
          </a-tag>
        </div>
        <div ref="chartRefs.loadDist" class="chart-container"></div>
      </div>
    </section>

    <!-- =============================================================== -->
    <!-- 3. 共性薄弱知识点 + 掌握度趋势图                                     -->
    <!-- =============================================================== -->
    <section class="content-row two-col">
      <!-- 共性薄弱知识点 Top 5 -->
      <div class="glass-card">
        <div class="card-header">
          <h3 class="card-title">
            <WarningOutlined style="margin-right: 6px; color: #ff4d4f" />
            共性薄弱知识点
          </h3>
          <span class="card-count">Top 5</span>
        </div>
        <div class="weak-kp-list">
          <div v-for="(item, idx) in weakKpsTop5" :key="item.knowledgePoint" class="weak-kp-item">
            <div class="weak-kp-rank" :class="'rank-' + (idx + 1)">{{ idx + 1 }}</div>
            <div class="weak-kp-info">
              <span class="weak-kp-name">{{ item.knowledgePoint }}</span>
              <span class="weak-kp-students">{{ item.studentCount }}人薄弱</span>
            </div>
            <div class="weak-kp-bar-wrap">
              <div class="weak-kp-bar-bg">
                <div
                  class="weak-kp-bar-fill"
                  :style="{
                    width: Math.round(item.avgMastery * 100) + '%',
                    background: item.avgMastery < 0.4 ? '#FF4D4F' : '#FA8C16'
                  }"
                ></div>
              </div>
              <span class="weak-kp-pct">{{ formatPct(item.avgMastery) }}</span>
            </div>
          </div>
          <a-empty
            v-if="weakKpsTop5.length === 0"
            description="暂无薄弱知识点数据"
            :imageStyle="{ height: '48px' }"
          />
        </div>
      </div>

      <!-- 全班掌握度趋势图 -->
      <div class="glass-card chart-card">
        <div class="card-header">
          <h3 class="card-title">
            <LineChartOutlined style="margin-right: 6px; color: #52c41a" />
            全班掌握度趋势
          </h3>
          <span class="card-count">近30天</span>
        </div>
        <div ref="chartRefs.trend" class="chart-container"></div>
      </div>
    </section>

    <!-- =============================================================== -->
    <!-- 6. 预警通知                                                        -->
    <!-- =============================================================== -->
    <section class="glass-card alerts-section">
      <div class="card-header">
        <h3 class="card-title">
          <ExclamationCircleOutlined style="margin-right: 6px; color: #ff4d4f" />
          预警通知
        </h3>
        <a-badge :count="alertCount" :number-style="{ backgroundColor: '#FF4D4F' }" />
      </div>
      <div v-if="alerts.length > 0" class="alerts-grid">
        <template v-for="alert in alerts" :key="alert.studentId">
          <div
            v-if="students.find((s) => s.id === alert.studentId)"
            class="alert-card"
            :class="'alert-' + alert.severity"
            @click="openStudentDetail(students.find((s) => s.id === alert.studentId)!)"
          >
            <div class="alert-header">
              <div class="alert-student">
                <span class="alert-avatar">
                  {{
                    (students.find((s) => s.id === alert.studentId)?.nickname || alert.name).charAt(
                      0
                    )
                  }}
                </span>
                <span class="alert-name">{{
                  students.find((s) => s.id === alert.studentId)?.nickname || alert.name
                }}</span>
              </div>
              <a-tag :color="alert.severity === 'danger' ? 'red' : 'orange'" size="small">
                {{
                  alert.reason === 'both'
                    ? '重点关注'
                    : alert.reason === 'highLoad'
                      ? '高负荷'
                      : '低掌握度'
                }}
              </a-tag>
            </div>
            <div class="alert-metrics">
              <div class="alert-metric">
                <span class="metric-label">掌握度</span>
                <span
                  class="metric-value"
                  :style="{ color: alert.avgMastery < 0.4 ? '#FF4D4F' : '#FA8C16' }"
                >
                  {{ formatPct(alert.avgMastery) }}
                </span>
              </div>
              <div class="alert-metric">
                <span class="metric-label">认知负荷</span>
                <span
                  class="metric-value"
                  :style="{ color: alert.cognitiveLoad > 0.7 ? '#FF4D4F' : '#FA8C16' }"
                >
                  {{ formatPct(alert.cognitiveLoad) }}
                </span>
              </div>
            </div>
            <div class="alert-reason">
              <template v-if="alert.reason === 'both'">
                ⚠ 认知负荷偏高且掌握度不足，建议重点关注
              </template>
              <template v-else-if="alert.reason === 'highLoad'">
                🔴 认知负荷持续偏高，可能超出承受范围
              </template>
              <template v-else> 📉 知识点掌握度低于班级平均水平 </template>
            </div>
          </div>
        </template>
      </div>
      <a-empty v-else description="暂无预警，全班学情状态良好" :imageStyle="{ height: '48px' }">
        <template #children>
          <CheckCircleOutlined style="color: #52c41a; font-size: 32px; margin-bottom: 8px" />
        </template>
      </a-empty>
    </section>

    <!-- =============================================================== -->
    <!-- 学生详情抽屉                                                        -->
    <!-- =============================================================== -->
    <a-drawer
      :open="detailDrawerVisible"
      :title="null"
      placement="right"
      :width="560"
      @close="closeDetail"
      :destroyOnClose="true"
      :bodyStyle="{ padding: '0' }"
    >
      <template #header>
        <div class="drawer-header">
          <span class="drawer-header-avatar">
            {{ selectedStudent?.nickname?.charAt(0) || '?' }}
          </span>
          <div>
            <span class="drawer-header-name">{{
              selectedStudent?.nickname || selectedStudent?.name || '—'
            }}</span>
            <span class="drawer-header-sub">学情详情</span>
          </div>
        </div>
      </template>

      <a-spin :spinning="detailLoading" v-if="studentDetail">
        <div class="drawer-body">
          <!-- 基本信息 -->
          <div class="drawer-section">
            <h4 class="drawer-section-title">基本信息</h4>
            <div class="detail-summary-cards">
              <div class="detail-card">
                <span class="dc-label">综合评分</span>
                <span
                  class="dc-value"
                  :style="{
                    color:
                      studentDetail.overallScore >= 80
                        ? '#52C41A'
                        : studentDetail.overallScore >= 60
                          ? '#4F7CFF'
                          : '#FF4D4F'
                  }"
                >
                  {{ studentDetail.overallScore }}/100
                </span>
              </div>
              <div class="detail-card">
                <span class="dc-label">学科</span>
                <span class="dc-value">{{ studentDetail.subject }}</span>
              </div>
              <div class="detail-card">
                <span class="dc-label">完成进度</span>
                <span class="dc-value">{{ studentDetail.summary.pathCompletion }}%</span>
              </div>
            </div>
          </div>

          <!-- 知识点掌握度 -->
          <div class="drawer-section">
            <h4 class="drawer-section-title">知识点掌握度</h4>
            <div class="detail-mastery-list">
              <div
                v-for="item in studentDetail.masteryLevels"
                :key="item.knowledgePoint"
                class="detail-mastery-item"
              >
                <div class="dm-header">
                  <span class="dm-name">{{ item.knowledgePoint }}</span>
                  <a-tag
                    :color="
                      item.level === 'excellent'
                        ? 'green'
                        : item.level === 'proficient'
                          ? 'blue'
                          : item.level === 'developing'
                            ? 'orange'
                            : 'red'
                    "
                    size="small"
                  >
                    {{
                      item.level === 'excellent'
                        ? '优秀'
                        : item.level === 'proficient'
                          ? '熟练'
                          : item.level === 'developing'
                            ? '发展中'
                            : '薄弱'
                    }}
                  </a-tag>
                </div>
                <a-progress
                  :percent="Math.round(item.mastery * 100)"
                  :strokeColor="
                    item.mastery >= 0.8
                      ? '#52C41A'
                      : item.mastery >= 0.6
                        ? '#4F7CFF'
                        : item.mastery >= 0.4
                          ? '#FA8C16'
                          : '#FF4D4F'
                  "
                  size="small"
                />
              </div>
            </div>
          </div>

          <!-- 认知负荷 -->
          <div class="drawer-section">
            <h4 class="drawer-section-title">认知负荷</h4>
            <div class="detail-load-grid">
              <div
                v-for="(val, key) in studentDetail.cognitiveLoad as Record<string, number>"
                :key="key"
                v-show="key !== 'overall'"
                class="detail-load-item"
              >
                <div class="dl-header">
                  <span
                    class="dl-dot"
                    :style="{ background: loadColorMap[key] || '#4F7CFF' }"
                  ></span>
                  <span class="dl-name">{{ loadLabelMap[key] || key }}</span>
                  <a-tag :color="ratingColorFromLoad(val)" size="small">{{
                    ratingFromLoad(val)
                  }}</a-tag>
                </div>
                <a-progress
                  :percent="Math.round(val * 100)"
                  :strokeColor="loadColorMap[key] || '#4F7CFF'"
                  size="small"
                  :showInfo="false"
                />
                <span class="dl-value">{{ Math.round(val * 100) }}%</span>
              </div>
            </div>
          </div>

          <!-- 薄弱点 -->
          <div class="drawer-section" v-if="studentDetail.weakPoints.length > 0">
            <h4 class="drawer-section-title">薄弱环节</h4>
            <div class="detail-weak-list">
              <div
                v-for="wp in studentDetail.weakPoints"
                :key="wp.knowledgePoint"
                class="detail-weak-item"
                :class="'severity-' + wp.severity"
              >
                <div class="dw-header">
                  <span class="dw-name">{{ wp.knowledgePoint }}</span>
                  <a-tag
                    :color="
                      wp.severity === 'severe'
                        ? 'red'
                        : wp.severity === 'moderate'
                          ? 'orange'
                          : 'blue'
                    "
                    size="small"
                  >
                    {{
                      wp.severity === 'severe'
                        ? '严重'
                        : wp.severity === 'moderate'
                          ? '中等'
                          : '轻度'
                    }}
                  </a-tag>
                </div>
                <p class="dw-reason">{{ wp.reason }}</p>
                <p class="dw-remediation" v-if="wp.suggestedRemediation">
                  <BulbOutlined style="margin-right: 4px" /> {{ wp.suggestedRemediation }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </a-spin>

      <div v-else class="drawer-empty">
        <a-empty description="暂无学生数据" />
      </div>
    </a-drawer>
  </div>
</template>

<style lang="less" scoped>
@import '@/assets/styles/variables.less';

.teacher-dashboard {
  padding: clamp(0.75rem, 1.5rem + 0.5vw, 2rem);
  max-width: var(--content-max-width-xl, 1400px);
  margin: 0 auto;
}

// ================================================================
//   Header
// ================================================================
.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;

    .header-icon {
      font-size: 28px;
      color: @brand-blue-500;
      padding: 12px;
      background: @brand-blue-500 15;
      border-radius: @radius-xl;
      backdrop-filter: blur(8px);
    }

    .header-title {
      font-size: 20px;
      font-weight: 700;
      color: #f8fafc;
      margin: 0;
      line-height: 1.2;
    }

    .header-subtitle {
      font-size: 13px;
      color: #94a3b8;
      margin: 2px 0 0;
    }
  }
}

// ================================================================
//   Overview Stat Cards
// ================================================================
.overview-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;

  @media (max-width: 1024px) {
    grid-template-columns: repeat(2, 1fr);
  }
  @media (max-width: 640px) {
    grid-template-columns: 1fr;
  }
}

.stat-card {
  .glass-card();
  display: flex;
  align-items: center;
  gap: clamp(0.5rem, 1rem + 0.2vw, 1.25rem);
  padding: clamp(0.75rem, 1.25rem + 0.3vw, 1.5rem);

  .stat-icon {
    width: clamp(2.5rem, 3.25rem + 0.5vw, 3.5rem);
    height: clamp(2.5rem, 3.25rem + 0.5vw, 3.5rem);
    border-radius: @radius-xl;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: clamp(1.25rem, 1.5rem + 0.3vw, 1.75rem);
    flex-shrink: 0;

    &.students-icon {
      background: rgba(74, 108, 247, 0.15);
      color: #4a6cf7;
    }
    &.mastery-icon {
      background: rgba(52, 211, 153, 0.15);
      color: #34d399;
    }
    &.load-icon {
      background: rgba(251, 191, 36, 0.15);
      color: #fbbf24;
    }
    &.completion-icon {
      background: rgba(167, 139, 250, 0.15);
      color: #a78bfa;
    }
  }

  .stat-body {
    display: flex;
    flex-direction: column;
    gap: 2px;

    .stat-label {
      font-size: @font-size-xs;
      color: #94a3b8;
    }

    .stat-value {
      font-size: clamp(1.375rem, 1.625rem + 0.5vw, 1.875rem);
      font-weight: 700;
      color: #f8fafc;
      line-height: 1.2;
    }

    .stat-sub {
      font-size: @font-size-xs;
      color: #94a3b8;
      display: flex;
      align-items: center;
      gap: 0.5rem;

      .load-detail {
        font-size: 0.6875rem;
        color: #ff4d4f;
        &::before {
          content: '· ';
        }
      }
    }
  }
}

// ================================================================
//   Two-column layout
// ================================================================
.content-row.two-col {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 16px;
  margin-bottom: 20px;

  @media (max-width: 1024px) {
    grid-template-columns: 1fr;
  }
}

// ================================================================
//   Glass Card
// ================================================================
.glass-card {
  .glass-card();
  padding: 20px;
  height: fit-content;
}

// ================================================================
//   Card Header
// ================================================================
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: clamp(0.5rem, 1rem + 0.2vw, 1.25rem);

  .card-title {
    font-size: clamp(0.875rem, 0.9375rem + 0.2vw, 1.0625rem);
    font-weight: 600;
    color: #f8fafc;
    margin: 0;
    display: flex;
    align-items: center;
  }

  .card-count {
    font-size: @font-size-xs;
    color: #94a3b8;
  }
}

// ================================================================
//   Student Table
// ================================================================
.student-table-card {
  overflow: hidden;
}

.student-table {
  :deep(.ant-table) {
    font-size: 13px;

    .ant-table-thead > tr > th {
      background: rgba(255, 255, 255, 0.04);
      font-weight: 600;
      font-size: 12px;
      color: #94a3b8;
      padding: 10px 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }

    .ant-table-tbody > tr > td {
      padding: 10px 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      color: #e2e8f0;
    }

    .ant-table-tbody > tr:hover > td {
      background: rgba(74, 108, 247, 0.06) !important;
    }
  }
}

.student-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  color: #f8fafc;

  .student-avatar-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #4f7cff;
    flex-shrink: 0;
  }
}

.mastery-cell {
  display: flex;
  align-items: center;
  gap: 8px;

  .mastery-bar-bg {
    width: 60px;
    height: 6px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 3px;
    overflow: hidden;

    .mastery-bar-fill {
      height: 100%;
      border-radius: 3px;
      transition: width 0.3s;
    }
  }

  .mastery-pct {
    font-size: 12px;
    font-weight: 600;
    min-width: 36px;
  }
}

.load-tag {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid;
}

.completion-cell {
  display: flex;
  align-items: center;
  gap: 8px;

  .completion-pct {
    font-size: 12px;
    color: #e2e8f0;
    font-weight: 500;
    min-width: 34px;
  }
}

.action-link {
  color: #d4a373;
  cursor: pointer;
  font-size: 13px;
  &:hover {
    color: #faedcd;
  }
}

// ================================================================
//   Chart Container
// ================================================================
.chart-card {
  min-height: 400px;
}

.chart-container {
  width: 100%;
  aspect-ratio: 16 / 10;
  min-height: 280px;
}

// ================================================================
//   Weak KP List
// ================================================================
.weak-kp-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.weak-kp-item {
  display: flex;
  align-items: center;
  gap: 12px;

  .weak-kp-rank {
    width: 24px;
    height: 24px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    color: #fff;
    flex-shrink: 0;

    &.rank-1 {
      background: #ff4d4f;
    }
    &.rank-2 {
      background: #ff7a45;
    }
    &.rank-3 {
      background: #fa8c16;
    }
    &.rank-4 {
      background: #ffc53d;
    }
    &.rank-5 {
      background: #ffec3d;
      color: #0a0d14;
    }
  }

  .weak-kp-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;

    .weak-kp-name {
      font-size: 13px;
      font-weight: 500;
      color: #e2e8f0;
      .ellipsis();
    }

    .weak-kp-students {
      font-size: 11px;
      color: #ff4d4f;
    }
  }

  .weak-kp-bar-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100px;
    flex-shrink: 0;

    .weak-kp-bar-bg {
      flex: 1;
      height: 6px;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 3px;
      overflow: hidden;

      .weak-kp-bar-fill {
        height: 100%;
        border-radius: 3px;
        transition: width 0.3s;
      }
    }

    .weak-kp-pct {
      font-size: 12px;
      font-weight: 600;
      color: #ff4d4f;
      min-width: 34px;
      text-align: right;
    }
  }
}

// ================================================================
//   Alerts Section
// ================================================================
.alerts-section {
  margin-bottom: 20px;
}

.alerts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.alert-card {
  padding: 16px;
  border-radius: @radius-lg;
  cursor: pointer;
  transition: all 0.25s ease;
  border: 1px solid;

  &.alert-danger {
    background: rgba(248, 113, 113, 0.08);
    border-color: rgba(248, 113, 113, 0.25);
    &:hover {
      box-shadow: 0 2px 12px rgba(248, 113, 113, 0.15);
      border-color: #f87171;
    }
  }

  &.alert-warning {
    background: rgba(251, 191, 36, 0.08);
    border-color: rgba(251, 191, 36, 0.25);
    &:hover {
      box-shadow: 0 2px 12px rgba(251, 191, 36, 0.15);
      border-color: #fbbf24;
    }
  }

  .alert-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;

    .alert-student {
      display: flex;
      align-items: center;
      gap: 8px;

      .alert-avatar {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: #4f7cff;
        color: #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 12px;
        font-weight: 600;
      }

      .alert-name {
        font-weight: 500;
        font-size: 14px;
        color: #f8fafc;
      }
    }
  }

  .alert-metrics {
    display: flex;
    gap: 16px;
    margin-bottom: 8px;

    .alert-metric {
      display: flex;
      flex-direction: column;
      gap: 2px;

      .metric-label {
        font-size: 11px;
        color: #94a3b8;
      }

      .metric-value {
        font-size: 16px;
        font-weight: 700;
      }
    }
  }

  .alert-reason {
    font-size: 12px;
    color: #94a3b8;
    line-height: 1.5;
    padding-top: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }
}

// ================================================================
//   Student Detail Drawer
// ================================================================
.drawer-header {
  display: flex;
  align-items: center;
  gap: 12px;

  .drawer-header-avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: linear-gradient(135deg, #4f7cff, #722ed1);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    font-weight: 700;
  }

  .drawer-header-name {
    display: block;
    font-size: 16px;
    font-weight: 600;
    color: #f8fafc;
  }

  .drawer-header-sub {
    display: block;
    font-size: 12px;
    color: #94a3b8;
  }
}

.drawer-body {
  padding: 16px 24px;
}

.drawer-empty {
  padding: 60px 24px;
  text-align: center;
}

.drawer-section {
  margin-bottom: 20px;

  &:last-child {
    margin-bottom: 0;
  }

  .drawer-section-title {
    font-size: 14px;
    font-weight: 600;
    color: #f8fafc;
    margin: 0 0 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
}

.detail-summary-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;

  .detail-card {
    text-align: center;
    padding: 14px 8px;
    background: rgba(255, 255, 255, 0.04);
    border-radius: @radius-lg;
    border: 1px solid rgba(255, 255, 255, 0.08);

    .dc-label {
      display: block;
      font-size: 11px;
      color: #94a3b8;
      margin-bottom: 4px;
    }

    .dc-value {
      display: block;
      font-size: 18px;
      font-weight: 700;
      color: #f8fafc;
    }
  }
}

.detail-mastery-list {
  display: flex;
  flex-direction: column;
  gap: 12px;

  .detail-mastery-item {
    .dm-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 4px;

      .dm-name {
        font-size: 13px;
        font-weight: 500;
        color: #e2e8f0;
      }
    }
  }
}

.detail-load-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;

  .detail-load-item {
    .dl-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 4px;

      .dl-dot {
        width: 8px;
        height: 8px;
        border-radius: 2px;
        flex-shrink: 0;
      }

      .dl-name {
        flex: 1;
        font-size: 13px;
        font-weight: 500;
        color: #e2e8f0;
      }
    }

    .dl-value {
      display: block;
      text-align: right;
      font-size: 12px;
      font-weight: 600;
      color: #94a3b8;
      margin-top: 2px;
    }
  }
}

.detail-weak-list {
  display: flex;
  flex-direction: column;
  gap: 12px;

  .detail-weak-item {
    padding: 12px;
    border-radius: @radius-md;
    border-left: 3px solid;

    &.severity-severe {
      background: rgba(248, 113, 113, 0.08);
      border-color: #f87171;
    }
    &.severity-moderate {
      background: rgba(251, 191, 36, 0.08);
      border-color: #fbbf24;
    }
    &.severity-mild {
      background: rgba(74, 108, 247, 0.08);
      border-color: #4a6cf7;
    }

    .dw-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;

      .dw-name {
        font-size: 13px;
        font-weight: 500;
        color: #e2e8f0;
      }
    }

    .dw-reason {
      font-size: 12px;
      color: #94a3b8;
      margin: 0 0 4px;
      line-height: 1.5;
    }

    .dw-remediation {
      font-size: 12px;
      color: #d4a373;
      margin: 0;
      display: flex;
      align-items: flex-start;
      line-height: 1.5;
    }
  }
}
</style>
