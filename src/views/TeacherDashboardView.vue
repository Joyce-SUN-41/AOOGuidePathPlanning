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
import { ref, computed, watch, onMounted, onUnmounted, nextTick, h } from 'vue'
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
  UserOutlined,
  BulbOutlined,
  HomeOutlined,
  ApartmentOutlined,
  FilterOutlined,
  SearchOutlined,
  ClearOutlined
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

// ---------- 工具栏筛选状态 ----------
const selectedClass = ref<string>('all')
const selectedMajors = ref<string[]>([])
const selectedStage = ref<string>('all')
const searchKeyword = ref<string>('')

const classOptions = [
  { label: '全部班级', value: 'all' },
  { label: '计科 2201 班', value: 'cs2201' },
  { label: '计科 2202 班', value: 'cs2202' },
  { label: '人工智能 2201 班', value: 'ai2201' },
  { label: '软工 2201 班', value: 'se2201' }
]

const majorOptions = [
  { label: '计算机科学', value: '计算机科学' },
  { label: '人工智能', value: '人工智能' },
  { label: '软件工程', value: '软件工程' },
  { label: '数据科学', value: '数据科学' }
]

const stageOptions = [
  { label: '全部阶段', value: 'all' },
  { label: '大一', value: '大一' },
  { label: '大二', value: '大二' },
  { label: '大三', value: '大三' },
  { label: '大四', value: '大四' }
]

// ---------- 面包屑导航 ----------
const breadcrumbLevel = ref<'dashboard' | 'class' | 'student'>('dashboard')

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

// ECharts —— 必须用「顶层 ref + 函数式 ref」绑定；
// `ref="chartRefs.loadDist"` 这类字符串路径在 <script setup> 中无效，
// 会导致容器永远拿不到 DOM，图表静默不渲染。
const loadDistEl = ref<HTMLDivElement | null>(null)
const trendEl = ref<HTMLDivElement | null>(null)
const weakKpEl = ref<HTMLDivElement | null>(null)

const chartInstances: Record<string, echarts.ECharts | null> = {
  loadDist: null,
  trend: null,
  weakKp: null
}
const resizeObservers: ResizeObserver[] = []

// ============================================================
//   表头配置
// ============================================================
/** 掌握度分档 —— 统一色板与文案 */
function masteryTier(v: number) {
  const pct = Math.round(v * 100)
  if (pct >= 80) return { pct, color: '#52C41A', label: '优秀' }
  if (pct >= 60) return { pct, color: '#4F7CFF', label: '良好' }
  if (pct >= 40) return { pct, color: '#FA8C16', label: '待提升' }
  return { pct, color: '#FF4D4F', label: '薄弱' }
}

/** 认知负荷分档 */
function loadTier(v: number) {
  const pct = Math.round(v * 100)
  if (pct > 70) return { pct, color: '#FF4D4F', label: '偏高' }
  if (pct > 50) return { pct, color: '#FA8C16', label: '适中' }
  return { pct, color: '#52C41A', label: '良好' }
}

/** 相对时间：3天内显示「N天前」，否则显示日期 */
function relativeDate(dateStr?: string): { text: string; stale: boolean } {
  if (!dateStr) return { text: '—', stale: true }
  const d = new Date(dateStr).getTime()
  if (Number.isNaN(d)) return { text: dateStr, stale: false }
  const days = Math.floor((Date.now() - d) / 86400000)
  if (days <= 0) return { text: '今天', stale: false }
  if (days === 1) return { text: '昨天', stale: false }
  if (days < 7) return { text: `${days} 天前`, stale: false }
  return { text: dateStr, stale: days > 14 }
}

const studentColumns = [
  {
    title: '学生',
    dataIndex: 'nickname',
    key: 'nickname',
    width: 190,
    sorter: true,
    customRender: ({ record }: { record: StudentSummary }) => {
      const display = record.nickname || record.name
      const tier = masteryTier(record.avgMastery)
      const anyR = record as StudentSummary & { major?: string; stage?: string }
      const meta = [anyR.stage, anyR.major].filter(Boolean).join(' · ') || record.subject || '—'
      return h('div', { class: 'stu-cell' }, [
        h(
          'span',
          { class: 'stu-avatar', style: { background: tier.color + '22', color: tier.color, borderColor: tier.color + '55' } },
          display.charAt(0)
        ),
        h('div', { class: 'stu-meta' }, [
          h('span', { class: 'stu-name' }, display),
          h('span', { class: 'stu-sub' }, meta)
        ])
      ])
    }
  },
  {
    title: '掌握度',
    dataIndex: 'avgMastery',
    key: 'avgMastery',
    width: 190,
    sorter: true,
    defaultSortOrder: 'descend' as const,
    customRender: ({ text }: { text: number }) => {
      const t = masteryTier(text)
      return h('div', { class: 'mastery-cell' }, [
        h('div', { class: 'mastery-bar-bg' }, [
          h('div', {
            class: 'mastery-bar-fill',
            style: {
              width: t.pct + '%',
              background: `linear-gradient(90deg, ${t.color}99, ${t.color})`
            }
          })
        ]),
        h('span', { class: 'mastery-pct', style: { color: t.color } }, t.pct + '%')
      ])
    }
  },
  {
    title: '认知负荷',
    dataIndex: 'cognitiveLoad',
    key: 'cognitiveLoad',
    width: 150,
    sorter: true,
    customRender: ({ text }: { text: number }) => {
      const t = loadTier(text)
      return h(
        'span',
        {
          class: 'load-tag',
          style: { color: t.color, background: t.color + '18', borderColor: t.color + '40' }
        },
        [h('i', { class: 'load-dot', style: { background: t.color } }), `${t.label} ${t.pct}%`]
      )
    }
  },
  {
    title: '路径完成度',
    dataIndex: 'pathCompletion',
    key: 'pathCompletion',
    width: 170,
    sorter: true,
    customRender: ({ text }: { text: number }) => {
      const pct = Math.round(text ?? 0)
      const color = pct >= 80 ? '#52C41A' : pct >= 50 ? '#4F7CFF' : '#FA8C16'
      return h('div', { class: 'completion-cell' }, [
        h('div', { class: 'completion-track' }, [
          h('div', { class: 'completion-fill', style: { width: pct + '%', background: color } })
        ]),
        h('span', { class: 'completion-pct', style: { color } }, pct + '%')
      ])
    }
  },
  {
    title: '薄弱点',
    dataIndex: 'weakPointCount',
    key: 'weakPointCount',
    width: 110,
    align: 'center' as const,
    sorter: true,
    customRender: ({ text }: { text: number }) => {
      const n = text ?? 0
      const color = n >= 5 ? '#FF4D4F' : n >= 3 ? '#FA8C16' : '#52C41A'
      return h('span', { class: 'weak-chip', style: { color, borderColor: color + '40', background: color + '15' } }, String(n))
    }
  },
  {
    title: '最近活跃',
    dataIndex: 'lastActiveDate',
    key: 'lastActiveDate',
    width: 130,
    sorter: true,
    customRender: ({ text }: { text: string }) => {
      const r = relativeDate(text)
      return h('span', { class: r.stale ? 'active-date stale' : 'active-date' }, r.text)
    }
  },
  {
    title: '操作',
    key: 'action',
    width: 100,
    fixed: 'right' as const,
    customRender: ({ record }: { record: StudentSummary }) =>
      h(
        'a',
        {
          class: 'action-link',
          onClick: (e: MouseEvent) => {
            e.stopPropagation()
            openStudentDetail(record)
          }
        },
        '查看详情'
      )
  }
]

/** 预警学生表格列 */
const alertColumns = [
  {
    title: '学生',
    dataIndex: 'displayName',
    key: 'displayName',
    width: 150,
    customRender: ({ record }: { record: any }) =>
      h('div', { class: 'stu-cell' }, [
        h(
          'span',
          {
            class: 'stu-avatar',
            style: {
              background: record.severity === 'danger' ? '#FF4D4F22' : '#FA8C1622',
              color: record.severity === 'danger' ? '#FF4D4F' : '#FA8C16',
              borderColor: record.severity === 'danger' ? '#FF4D4F55' : '#FA8C1655'
            }
          },
          String(record.displayName).charAt(0)
        ),
        h('span', { class: 'stu-name' }, record.displayName)
      ])
  },
  {
    title: '预警等级',
    dataIndex: 'severity',
    key: 'severity',
    width: 110,
    customRender: ({ text }: { text: string }) => {
      const isDanger = text === 'danger'
      const color = isDanger ? '#FF4D4F' : '#FA8C16'
      return h(
        'span',
        { class: 'sev-tag', style: { color, background: color + '18', borderColor: color + '40' } },
        isDanger ? '高危' : '关注'
      )
    }
  },
  {
    title: '预警原因',
    dataIndex: 'reason',
    key: 'reason',
    width: 200,
    customRender: ({ text }: { text: string }) =>
      h(
        'span',
        { class: 'reason-text' },
        text === 'both'
          ? '认知负荷偏高且掌握度不足'
          : text === 'highLoad'
            ? '认知负荷持续偏高'
            : '知识点掌握度低于班级均值'
      )
  },
  {
    title: '掌握度',
    dataIndex: 'avgMastery',
    key: 'avgMastery',
    width: 110,
    align: 'right' as const,
    customRender: ({ text }: { text: number }) => {
      const t = masteryTier(text)
      return h('span', { style: { color: t.color, fontWeight: 700 } }, t.pct + '%')
    }
  },
  {
    title: '认知负荷',
    dataIndex: 'cognitiveLoad',
    key: 'cognitiveLoad',
    width: 110,
    align: 'right' as const,
    customRender: ({ text }: { text: number }) => {
      const t = loadTier(text)
      return h('span', { style: { color: t.color, fontWeight: 700 } }, t.pct + '%')
    }
  },
  {
    title: '操作',
    key: 'action',
    width: 100,
    align: 'center' as const,
    customRender: ({ record }: { record: any }) =>
      h(
        'a',
        {
          class: 'action-link',
          onClick: (e: MouseEvent) => {
            e.stopPropagation()
            const stu = students.value.find((s) => s.id === record.studentId)
            if (stu) openStudentDetail(stu)
            else message.info('该学生详情暂不可用')
          }
        },
        '查看'
      )
  }
]

// ============================================================
//   Computed
// ============================================================
/**
 * 筛选后的学生列表 —— 班级 / 专业(多选) / 学习阶段 / 关键词
 * 后端字段可能缺失（className / major / stage），缺失时视为「不参与该维度过滤」，
 * 保证向后兼容：老数据不会因为新筛选器而被误隐藏。
 */
const filteredStudents = computed(() => {
  return students.value.filter((s) => {
    const anyS = s as StudentSummary & {
      classId?: string
      className?: string
      major?: string
      stage?: string
    }

    if (selectedClass.value !== 'all' && anyS.classId && anyS.classId !== selectedClass.value) {
      return false
    }
    if (selectedMajors.value.length > 0 && anyS.major && !selectedMajors.value.includes(anyS.major)) {
      return false
    }
    if (selectedStage.value !== 'all' && anyS.stage && anyS.stage !== selectedStage.value) {
      return false
    }
    if (searchKeyword.value.trim()) {
      const kw = searchKeyword.value.trim().toLowerCase()
      const hit =
        (s.nickname || '').toLowerCase().includes(kw) || (s.name || '').toLowerCase().includes(kw)
      if (!hit) return false
    }
    return true
  })
})

/** 当前筛选条件的签名，用于驱动图表联动刷新 */
const filterSignature = computed(
  () =>
    `${selectedClass.value}|${selectedMajors.value.join(',')}|${selectedStage.value}|${searchKeyword.value}`
)

const hasActiveFilter = computed(
  () =>
    selectedClass.value !== 'all' ||
    selectedMajors.value.length > 0 ||
    selectedStage.value !== 'all' ||
    !!searchKeyword.value.trim()
)

const currentClassLabel = computed(
  () => classOptions.find((c) => c.value === selectedClass.value)?.label ?? '全部班级'
)

const loadDistData = computed(() => {
  return filteredStudents.value.map((s) => ({
    name: s.nickname || s.name,
    value: Math.round(s.cognitiveLoad * 100),
    color: s.cognitiveLoad > 0.7 ? '#FF4D4F' : s.cognitiveLoad > 0.5 ? '#FA8C16' : '#4F7CFF'
  }))
})

const highLoadStudents = computed(() =>
  filteredStudents.value.filter((s) => s.cognitiveLoad > 0.7)
)

/** 预警学生表格数据 —— danger 优先置顶，其次 warning */
const alertTableData = computed(() => {
  const visibleIds = new Set(filteredStudents.value.map((s) => s.id))
  const severityRank: Record<string, number> = { danger: 0, warning: 1, info: 2 }
  return alerts.value
    .filter((a) => visibleIds.size === 0 || visibleIds.has(a.studentId))
    .map((a) => {
      const stu = students.value.find((s) => s.id === a.studentId)
      return {
        ...a,
        key: a.studentId,
        displayName: stu?.nickname || a.nickname || a.name,
        pathCompletion: stu?.pathCompletion ?? 0
      }
    })
    .sort((x, y) => {
      const r = (severityRank[x.severity] ?? 9) - (severityRank[y.severity] ?? 9)
      if (r !== 0) return r
      return x.avgMastery - y.avgMastery
    })
})

const alertCount = computed(() => alertTableData.value.length)
const weakKpsTop5 = computed(() => weakKps.value.slice(0, 5))

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
    const res = await teacherApi.getStudents({
      sortBy: studentsSortField.value,
      order: studentsSortOrder.value
    })
    // 接口成功但返回空数组时同样回退到演示数据，
    // 否则「认知负荷分布」等依赖学生集合的图表会是一片空白。
    students.value = Array.isArray(res) && res.length > 0 ? res : getFallbackStudents()
  } catch {
    students.value = getFallbackStudents()
  }
  tableLoading.value = false
}

async function loadWeakKps() {
  try {
    const res = await teacherApi.getWeakKps(5)
    weakKps.value = Array.isArray(res) && res.length > 0 ? res : getFallbackWeakKps()
  } catch {
    weakKps.value = getFallbackWeakKps()
  }
}

async function loadMasteryTrend() {
  try {
    const res = await teacherApi.getMasteryTrend(30)
    // 少于 2 个点无法构成趋势线，视为无效数据
    masteryTrend.value = Array.isArray(res) && res.length >= 2 ? res : getFallbackTrend()
  } catch {
    masteryTrend.value = getFallbackTrend()
  }
}

async function loadAlerts() {
  try {
    const res = await teacherApi.getAlerts()
    alerts.value = Array.isArray(res) ? res : []
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
  breadcrumbLevel.value = 'student'
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
  breadcrumbLevel.value = hasActiveFilter.value ? 'class' : 'dashboard'
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
  const el = loadDistEl.value
  if (!el || el.clientWidth === 0) return

  if (chartInstances['loadDist']) {
    chartInstances['loadDist']!.dispose()
    chartInstances['loadDist'] = null
  }
  const chart = echarts.init(el)
  chartInstances['loadDist'] = chart

  const dataItems = loadDistData.value

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(20,27,43,0.95)',
      borderColor: 'rgba(255,255,255,0.12)',
      textStyle: { color: '#E2E8F0', fontSize: 12 },
      formatter: (params: any) => {
        const item = params[0]
        const color = item.color || '#4F7CFF'
        return `<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${color};margin-right:6px;"></span>
          <b style="color:#F8FAFC">${item.name}</b><br/>
          认知负荷：<b style="color:${color}">${item.value}%</b>
          ${item.value > 70 ? '<br/><span style="color:#FF4D4F">超过警戒线</span>' : ''}`
      }
    },
    grid: { top: 24, right: 20, bottom: 62, left: 52, containLabel: false },
    xAxis: {
      type: 'category',
      data: dataItems.map((d) => d.name),
      axisLabel: { rotate: 38, fontSize: 11, color: '#94A3B8', hideOverlap: true },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.15)' } },
      axisTick: { alignWithLabel: true, lineStyle: { color: 'rgba(255,255,255,0.15)' } }
    },
    yAxis: {
      type: 'value',
      name: '负荷 %',
      nameLocation: 'middle',
      nameGap: 38,
      nameTextStyle: { color: '#CBD5E1', fontSize: 12 },
      min: 0,
      max: 100,
      axisLabel: { fontSize: 11, color: '#94A3B8' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)', type: 'dashed' } }
    },
    series: [
      {
        type: 'bar',
        data: dataItems.map((d) => ({
          value: d.value,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: d.color },
              { offset: 1, color: d.color + '55' }
            ]),
            borderRadius: [6, 6, 0, 0]
          }
        })),
        barMaxWidth: 36,
        barMinWidth: 6,
        emphasis: { itemStyle: { shadowBlur: 12, shadowColor: 'rgba(0,0,0,0.4)' } },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#FF4D4F', type: 'dashed', width: 2 },
          label: {
            formatter: '警戒线 70%',
            position: 'insideEndTop',
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
//   ECharts：共性薄弱知识点水平条形图（按薄弱学生数降序 + 掌握度梯度着色）
// ============================================================
function initWeakKpChart() {
  const el = weakKpEl.value
  if (!el || el.clientWidth === 0) return

  if (chartInstances['weakKp']) {
    chartInstances['weakKp']!.dispose()
    chartInstances['weakKp'] = null
  }
  const chart = echarts.init(el)
  chartInstances['weakKp'] = chart

  // Y 轴自下而上绘制，故按升序排列可使最大值显示在顶部
  const sorted = [...weakKpsTop5.value].sort((a, b) => a.studentCount - b.studentCount)
  const names = sorted.map((d) => d.knowledgePoint)
  const counts = sorted.map((d) => d.studentCount)
  const masteries = sorted.map((d) => d.avgMastery)

  /** 掌握度梯度着色：越低越红，越高越偏橙/蓝 */
  const gradeColor = (m: number) => {
    if (m < 0.35) return '#FF4D4F'
    if (m < 0.45) return '#FF7A45'
    if (m < 0.55) return '#FA8C16'
    if (m < 0.65) return '#FAAD14'
    return '#4F7CFF'
  }

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(20,27,43,0.95)',
      borderColor: 'rgba(255,255,255,0.12)',
      textStyle: { color: '#E2E8F0', fontSize: 12 },
      formatter: (params: any) => {
        const p = params[0]
        const i = p.dataIndex as number
        const m = masteries[i] ?? 0
        const c = gradeColor(m)
        return `<b style="color:#F8FAFC">${names[i] ?? ''}</b><br/>
          薄弱学生：<b style="color:${c}">${counts[i] ?? 0} 人</b><br/>
          平均掌握度：<b style="color:${c}">${Math.round(m * 100)}%</b>`
      }
    },
    grid: { top: 28, right: 56, bottom: 34, left: 8, containLabel: true },
    xAxis: {
      type: 'value',
      name: '薄弱学生数',
      nameLocation: 'middle',
      nameGap: 26,
      nameTextStyle: { color: '#CBD5E1', fontSize: 12 },
      minInterval: 1,
      axisLabel: { color: '#94A3B8', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)', type: 'dashed' } }
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLabel: {
        color: '#CBD5E1',
        fontSize: 12,
        width: 96,
        overflow: 'truncate'
      },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.15)' } },
      axisTick: { show: false }
    },
    series: [
      {
        type: 'bar',
        data: counts.map((v, i) => {
          const c = gradeColor(masteries[i] ?? 0)
          return {
            value: v,
            itemStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: c + '66' },
                { offset: 1, color: c }
              ]),
              borderRadius: [0, 6, 6, 0]
            }
          }
        }),
        barMaxWidth: 22,
        label: {
          show: true,
          position: 'right',
          color: '#E2E8F0',
          fontSize: 11,
          fontWeight: 600,
          formatter: (p: any) =>
            `${p.value}人 · ${Math.round((masteries[p.dataIndex as number] ?? 0) * 100)}%`
        },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.4)' } }
      }
    ]
  })

  bindResize(chart, el)
}

// ============================================================
//   ECharts：全班掌握度趋势图
// ============================================================
function initTrendChart() {
  const el = trendEl.value
  if (!el || el.clientWidth === 0) return

  if (chartInstances['trend']) {
    chartInstances['trend']!.dispose()
    chartInstances['trend'] = null
  }
  const chart = echarts.init(el)
  chartInstances['trend'] = chart

  const dates = masteryTrend.value.map((d) => d.date.slice(5))
  const values = masteryTrend.value.map((d) => Math.round(d.avgMastery * 100))
  const counts = masteryTrend.value.map((d) => d.diagnosisCount)

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(20,27,43,0.95)',
      borderColor: 'rgba(255,255,255,0.12)',
      textStyle: { color: '#E2E8F0', fontSize: 12 },
      formatter: (params: any) => {
        const item = params[0]
        const idx = item.dataIndex
        return `<b style="color:#F8FAFC">${masteryTrend.value[idx]?.date ?? ''}</b><br/>
          平均掌握度：<b style="color:#4F7CFF">${item.value}%</b><br/>
          参与诊断人数：${counts[idx] ?? 0} 人`
      }
    },
    grid: { top: 24, right: 24, bottom: 44, left: 58, containLabel: false },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dates,
      axisLabel: {
        fontSize: 10,
        color: '#94A3B8',
        hideOverlap: true,
        interval: Math.max(0, Math.floor(dates.length / 8) - 1)
      },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.15)' } }
    },
    yAxis: {
      type: 'value',
      name: '掌握度 %',
      nameLocation: 'middle',
      nameGap: 42,
      nameTextStyle: { color: '#CBD5E1', fontSize: 12 },
      min: 0,
      max: 100,
      axisLabel: { fontSize: 11, color: '#94A3B8' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)', type: 'dashed' } }
    },
    series: [
      {
        type: 'line',
        data: values,
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        showSymbol: dates.length <= 40,
        lineStyle: { color: '#4F7CFF', width: 3 },
        itemStyle: {
          color: '#4F7CFF',
          borderColor: '#141B2B',
          borderWidth: 2
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(79,124,255,0.28)' },
            { offset: 1, color: 'rgba(79,124,255,0.02)' }
          ])
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#D4A373', type: 'dashed', width: 2 },
          label: {
            formatter: '目标 80%',
            position: 'insideEndTop',
            fontSize: 11,
            color: '#D4A373',
            fontWeight: 600
          },
          data: [{ yAxis: 80 }]
        }
      }
    ]
  })

  bindResize(chart, el)
}

/**
 * 初始化全部图表。
 * 用 rAF + nextTick 双保险，确保容器已完成布局（clientWidth > 0）后再 init，
 * 否则 ECharts 会以 0 宽度初始化而看不到任何内容。
 */
async function initAllCharts() {
  await nextTick()
  requestAnimationFrame(() => {
    initLoadDistChart()
    initTrendChart()
    initWeakKpChart()
  })
}

function bindResize(chart: echarts.ECharts, el: HTMLElement) {
  const observer = new ResizeObserver(() => {
    if (el.clientWidth > 0) chart.resize()
  })
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
  const classIds = ['cs2201', 'cs2202', 'ai2201', 'se2201']
  const majors = ['计算机科学', '人工智能', '软件工程', '数据科学']
  const stages = ['大一', '大二', '大三', '大四']
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
    overallScore: Math.floor(30 + Math.random() * 65),
    classId: classIds[i % classIds.length],
    major: majors[i % majors.length],
    stage: stages[i % stages.length]
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
//   筛选联动 —— 任一筛选条件变化时重绘依赖学生集合的图表
// ============================================================
watch(filterSignature, () => {
  nextTick(() => {
    initLoadDistChart()
  })
})

watch(
  () => weakKps.value,
  () => {
    nextTick(() => initWeakKpChart())
  }
)

function resetFilters() {
  selectedClass.value = 'all'
  selectedMajors.value = []
  selectedStage.value = 'all'
  searchKeyword.value = ''
}

// ============================================================
//   面包屑导航
// ============================================================
function goBreadcrumb(level: 'dashboard' | 'class') {
  if (level === 'dashboard') {
    detailDrawerVisible.value = false
    resetFilters()
    breadcrumbLevel.value = 'dashboard'
  } else {
    detailDrawerVisible.value = false
    breadcrumbLevel.value = 'class'
  }
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
    <!-- 面包屑导航 -->
    <a-breadcrumb class="dashboard-breadcrumb">
      <a-breadcrumb-item>
        <a @click.prevent="goBreadcrumb('dashboard')">
          <HomeOutlined style="margin-right: 4px" />仪表盘
        </a>
      </a-breadcrumb-item>
      <a-breadcrumb-item v-if="breadcrumbLevel !== 'dashboard' || hasActiveFilter">
        <a @click.prevent="goBreadcrumb('class')">
          <ApartmentOutlined style="margin-right: 4px" />{{ currentClassLabel }}
        </a>
      </a-breadcrumb-item>
      <a-breadcrumb-item v-if="breadcrumbLevel === 'student' && selectedStudent">
        <span class="crumb-current">
          <UserOutlined style="margin-right: 4px" />{{
            selectedStudent.nickname || selectedStudent.name
          }}
        </span>
      </a-breadcrumb-item>
    </a-breadcrumb>

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

    <!-- =============================================================== -->
    <!-- 筛选工具栏：班级 / 专业(多选) / 学习阶段 / 关键词                     -->
    <!-- =============================================================== -->
    <section class="filter-toolbar">
      <div class="filter-toolbar-label">
        <FilterOutlined />
        <span>数据筛选</span>
      </div>

      <a-select
        v-model:value="selectedClass"
        :options="classOptions"
        class="filter-select filter-class"
        placeholder="选择班级"
        size="middle"
      />

      <a-select
        v-model:value="selectedMajors"
        :options="majorOptions"
        mode="multiple"
        class="filter-select filter-major"
        placeholder="专业筛选（可多选）"
        :max-tag-count="2"
        allow-clear
        size="middle"
      />

      <a-select
        v-model:value="selectedStage"
        :options="stageOptions"
        class="filter-select filter-stage"
        placeholder="学习阶段"
        size="middle"
      />

      <a-input
        v-model:value="searchKeyword"
        class="filter-search"
        placeholder="搜索学生姓名"
        allow-clear
        size="middle"
      >
        <template #prefix><SearchOutlined style="color: #94a3b8" /></template>
      </a-input>

      <a-button v-if="hasActiveFilter" type="text" class="filter-reset" @click="resetFilters">
        <template #icon><ClearOutlined /></template>
        重置
      </a-button>

      <span class="filter-result-count">
        匹配 <b>{{ filteredStudents.length }}</b> / {{ students.length }} 人
      </span>
    </section>

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
          <span class="card-count">共 {{ filteredStudents.length }} 人</span>
        </div>
        <a-table
          :dataSource="filteredStudents"
          :columns="studentColumns"
          :loading="tableLoading"
          :pagination="{
            pageSize: 8,
            showSizeChanger: true,
            pageSizeOptions: ['8', '10', '15', '20'],
            size: 'small',
            showTotal: (total: number) => `共 ${total} 人`
          }"
          :scroll="{ x: 1040 }"
          rowKey="id"
          size="middle"
          :rowClassName="
            (record: StudentSummary) =>
              record.cognitiveLoad > 0.7 || record.avgMastery < 0.4 ? 'row-attention' : ''
          "
          :customRow="
            (record: StudentSummary) => ({
              style: { cursor: 'pointer' },
              onClick: () => openStudentDetail(record)
            })
          "
          @change="handleTableChange"
          class="student-table"
        >
          <template #emptyText>
            <a-empty
              :description="
                hasActiveFilter ? '当前筛选条件下没有匹配的学生' : '暂无学生数据'
              "
              :imageStyle="{ height: '48px' }"
            />
          </template>
        </a-table>
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
        <div :ref="(el) => (loadDistEl = el as HTMLDivElement)" class="chart-container"></div>
      </div>
    </section>

    <!-- =============================================================== -->
    <!-- 3. 共性薄弱知识点 + 掌握度趋势图                                     -->
    <!-- =============================================================== -->
    <section class="content-row two-col">
      <!-- 共性薄弱知识点 Top 5 —— ECharts 水平条形图 -->
      <div class="glass-card chart-card">
        <div class="card-header">
          <h3 class="card-title">
            <WarningOutlined style="margin-right: 6px; color: #ff4d4f" />
            共性薄弱知识点
          </h3>
          <span class="card-count">Top 5 · 按薄弱人数降序</span>
        </div>
        <div
          v-show="weakKpsTop5.length > 0"
          :ref="(el) => (weakKpEl = el as HTMLDivElement)"
          class="chart-container"
        ></div>
        <a-empty
          v-if="weakKpsTop5.length === 0"
          description="暂无薄弱知识点数据"
          :imageStyle="{ height: '48px' }"
        />
        <div v-if="weakKpsTop5.length > 0" class="chart-legend-hint">
          柱条颜色按平均掌握度梯度着色：越红表示掌握度越低
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
        <div :ref="(el) => (trendEl = el as HTMLDivElement)" class="chart-container"></div>
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
      <a-table
        v-if="alertTableData.length > 0"
        :dataSource="alertTableData"
        :columns="alertColumns"
        :pagination="false"
        :scroll="{ x: 780 }"
        rowKey="key"
        size="middle"
        class="alert-table"
        :rowClassName="(record: any) => 'alert-row alert-row-' + record.severity"
        :customRow="
          (record: any) => ({
            style: { cursor: 'pointer' },
            onClick: () => {
              const stu = students.find((s) => s.id === record.studentId)
              if (stu) openStudentDetail(stu)
            }
          })
        "
      />
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
//   Breadcrumb
// ================================================================
.dashboard-breadcrumb {
  margin-bottom: 12px;
  font-size: 13px;

  :deep(.ant-breadcrumb-separator) {
    color: rgba(255, 255, 255, 0.28);
  }

  :deep(a) {
    color: #94a3b8;
    transition: color 0.2s ease;
    display: inline-flex;
    align-items: center;

    &:hover {
      color: #d4a373;
    }
  }

  .crumb-current {
    color: #f8fafc;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
  }
}

// ================================================================
//   Filter Toolbar
// ================================================================
.filter-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px 16px;
  margin-bottom: 20px;
  border-radius: @radius-xl;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(10px);

  .filter-toolbar-label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
    color: #cbd5e1;
    padding-right: 6px;
    margin-right: 2px;
    border-right: 1px solid rgba(255, 255, 255, 0.1);

    .anticon {
      color: #d4a373;
    }
  }

  .filter-select {
    &.filter-class {
      min-width: 160px;
    }
    &.filter-major {
      min-width: 230px;
      flex: 1 1 230px;
      max-width: 340px;
    }
    &.filter-stage {
      min-width: 130px;
    }
  }

  .filter-search {
    width: 190px;
  }

  .filter-reset {
    color: #94a3b8;

    &:hover {
      color: #d4a373;
    }
  }

  .filter-result-count {
    margin-left: auto;
    font-size: 12px;
    color: #94a3b8;
    white-space: nowrap;

    b {
      color: #d4a373;
      font-size: 14px;
      font-weight: 700;
    }
  }

  // 深色主题下的 antd 控件适配
  :deep(.ant-select-selector),
  :deep(.ant-input-affix-wrapper) {
    background: rgba(255, 255, 255, 0.05) !important;
    border-color: rgba(255, 255, 255, 0.12) !important;
    color: #e2e8f0 !important;
  }

  :deep(.ant-select-selection-item) {
    color: #e2e8f0;
  }

  :deep(.ant-select-multiple .ant-select-selection-item) {
    background: rgba(212, 163, 115, 0.18);
    border-color: rgba(212, 163, 115, 0.35);
    color: #f0d5b8;
  }

  :deep(.ant-select-selection-placeholder),
  :deep(.ant-input::placeholder) {
    color: #64748b;
  }

  :deep(.ant-input) {
    background: transparent !important;
    color: #e2e8f0 !important;
  }

  :deep(.ant-select-arrow),
  :deep(.ant-select-clear) {
    color: #94a3b8;
    background: transparent;
  }

  @media (max-width: 900px) {
    .filter-select,
    .filter-search {
      flex: 1 1 100%;
      max-width: none;
      width: 100%;
    }
    .filter-result-count {
      margin-left: 0;
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

.student-table,
.alert-table {
  :deep(.ant-table) {
    background: transparent;
    font-size: 13px;

    .ant-table-thead > tr > th {
      background: rgba(255, 255, 255, 0.04);
      font-weight: 600;
      font-size: 12px;
      letter-spacing: 0.02em;
      color: #94a3b8;
      padding: 11px 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);

      &::before {
        display: none !important;
      }
    }

    .ant-table-tbody > tr > td {
      padding: 11px 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      color: #e2e8f0;
      background: transparent;
      transition: background 0.18s ease;
    }

    .ant-table-tbody > tr:hover > td {
      background: rgba(74, 108, 247, 0.09) !important;
    }

    // 需关注学生：左侧金色标识条
    .ant-table-tbody > tr.row-attention > td:first-child {
      box-shadow: inset 3px 0 0 rgba(212, 163, 115, 0.75);
    }

    .ant-table-placeholder > td {
      background: transparent !important;
      border-bottom: none;
    }

    .ant-table-cell-fix-right,
    .ant-table-cell-fix-left {
      background: #141b2b !important;
    }
  }

  :deep(.ant-table-column-sorter) {
    color: #64748b;
  }

  :deep(.ant-pagination) {
    margin: 14px 0 2px;

    .ant-pagination-item a,
    .ant-pagination-item-link,
    .ant-pagination-total-text {
      color: #94a3b8;
    }

    .ant-pagination-item {
      background: rgba(255, 255, 255, 0.04);
      border-color: rgba(255, 255, 255, 0.1);

      &-active {
        background: rgba(212, 163, 115, 0.18);
        border-color: rgba(212, 163, 115, 0.5);

        a {
          color: #f0d5b8;
        }
      }
    }
  }
}

// ---------- 学生单元格 ----------
.stu-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;

  .stu-avatar {
    width: 30px;
    height: 30px;
    flex-shrink: 0;
    border-radius: 9px;
    border: 1px solid;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    font-weight: 700;
  }

  .stu-meta {
    display: flex;
    flex-direction: column;
    min-width: 0;
    line-height: 1.3;
  }

  .stu-name {
    font-size: 13px;
    font-weight: 600;
    color: #f8fafc;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .stu-sub {
    font-size: 11px;
    color: #64748b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.mastery-cell {
  display: flex;
  align-items: center;
  gap: 10px;

  .mastery-bar-bg {
    flex: 1;
    min-width: 60px;
    height: 7px;
    background: rgba(255, 255, 255, 0.09);
    border-radius: 4px;
    overflow: hidden;

    .mastery-bar-fill {
      height: 100%;
      border-radius: 4px;
      transition: width 0.35s ease;
    }
  }

  .mastery-pct {
    font-size: 12px;
    font-weight: 700;
    min-width: 38px;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
}

.load-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 9px;
  border-radius: 999px;
  border: 1px solid;
  white-space: nowrap;

  .load-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }
}

.completion-cell {
  display: flex;
  align-items: center;
  gap: 10px;

  .completion-track {
    flex: 1;
    min-width: 54px;
    height: 7px;
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.09);
    overflow: hidden;

    .completion-fill {
      height: 100%;
      border-radius: 4px;
      transition: width 0.35s ease;
    }
  }

  .completion-pct {
    font-size: 12px;
    font-weight: 700;
    min-width: 36px;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
}

.weak-chip {
  display: inline-block;
  min-width: 26px;
  padding: 2px 7px;
  border-radius: 6px;
  border: 1px solid;
  font-size: 12px;
  font-weight: 700;
  text-align: center;
}

.active-date {
  font-size: 12px;
  color: #cbd5e1;

  &.stale {
    color: #64748b;
  }
}

.sev-tag {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid;
  font-size: 11px;
  font-weight: 700;
}

.reason-text {
  font-size: 12px;
  color: #cbd5e1;
}

.action-link {
  color: #d4a373;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  &:hover {
    color: #faedcd;
  }
}

// ================================================================
//   Alert Table Row Highlighting
// ================================================================
.alert-table {
  :deep(.ant-table-tbody > tr.alert-row-danger > td) {
    background: rgba(255, 77, 79, 0.1);
  }
  :deep(.ant-table-tbody > tr.alert-row-danger > td:first-child) {
    box-shadow: inset 3px 0 0 #ff4d4f;
  }
  :deep(.ant-table-tbody > tr.alert-row-danger:hover > td) {
    background: rgba(255, 77, 79, 0.17) !important;
  }

  :deep(.ant-table-tbody > tr.alert-row-warning > td) {
    background: rgba(250, 140, 22, 0.09);
  }
  :deep(.ant-table-tbody > tr.alert-row-warning > td:first-child) {
    box-shadow: inset 3px 0 0 #fa8c16;
  }
  :deep(.ant-table-tbody > tr.alert-row-warning:hover > td) {
    background: rgba(250, 140, 22, 0.16) !important;
  }
}

// ================================================================
//   Chart Container
// ================================================================
.chart-card {
  min-height: 400px;
  display: flex;
  flex-direction: column;
}

.chart-container {
  width: 100%;
  flex: 1;
  aspect-ratio: 16 / 10;
  min-height: 280px;
}

.chart-legend-hint {
  margin-top: 8px;
  font-size: 11px;
  color: #64748b;
  text-align: center;
}

// ================================================================
//   Alerts Section
// ================================================================
.alerts-section {
  margin-bottom: 20px;
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
