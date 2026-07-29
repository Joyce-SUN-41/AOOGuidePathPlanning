<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { message } from 'ant-design-vue'
import {
  ExperimentOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
  BulbOutlined,
  RocketOutlined,
  TrophyOutlined,
  ArrowRightOutlined,
  ReloadOutlined,
  BarChartOutlined,
  WarningOutlined,
  AimOutlined,
  PlayCircleOutlined,
  BookOutlined
} from '@ant-design/icons-vue'
import { diagnosisApi } from '@/api/modules/diagnosis'
import { pathApi } from '@/api/modules/path'
import type {
  DiagnosisQuestion,
  DiagnosisAnswer,
  DiagnosisResult,
  MasteryItem,
  CognitiveLoadProfile,
  WeakPoint
} from '@/types'

const router = useRouter()

// ═══════════════════════════════════════════
// Mock 题库（15 道题，5 个知识点，每个知识点 3 题）
// ═══════════════════════════════════════════
const MOCK_QUESTIONS: DiagnosisQuestion[] = [
  // ===== 知识点 1：一元二次方程 =====
  {
    id: 'q1', topic: 'k1_一元二次方程', difficulty: 1,
    title: '方程 x² - 5x + 6 = 0 的解是？',
    options: [
      { id: 'a', text: 'x = 2 或 x = 3', weight: 1 },
      { id: 'b', text: 'x = -2 或 x = -3', weight: 0 },
      { id: 'c', text: 'x = 1 或 x = 6', weight: 0 },
      { id: 'd', text: 'x = -1 或 x = -6', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q2', topic: 'k1_一元二次方程', difficulty: 2,
    title: '若方程 2x² + kx + 3 = 0 有两个相等的实数根，则 k 的值为？',
    options: [
      { id: 'a', text: 'k = ±2√3', weight: 0 },
      { id: 'b', text: 'k = ±2√6', weight: 1 },
      { id: 'c', text: 'k = ±√6', weight: 0 },
      { id: 'd', text: 'k = ±3√2', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q3', topic: 'k1_一元二次方程', difficulty: 3,
    title: '关于 x 的方程 (m-1)x² + 2mx + (m+1) = 0，当方程有两个不相等的实数根时，m 的取值范围是？',
    options: [
      { id: 'a', text: 'm > 1/2 且 m ≠ 1', weight: 1 },
      { id: 'b', text: 'm > 1/2', weight: 0 },
      { id: 'c', text: 'm < 1/2', weight: 0 },
      { id: 'd', text: 'm ≠ 1', weight: 0 }
    ],
    type: 'single'
  },

  // ===== 知识点 2：函数图像与性质 =====
  {
    id: 'q4', topic: 'k2_函数图像与性质', difficulty: 1,
    title: '一次函数 y = 2x - 3 的图像不经过哪个象限？',
    options: [
      { id: 'a', text: '第一象限', weight: 0 },
      { id: 'b', text: '第二象限', weight: 1 },
      { id: 'c', text: '第三象限', weight: 0 },
      { id: 'd', text: '第四象限', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q5', topic: 'k2_函数图像与性质', difficulty: 2,
    title: '二次函数 y = x² - 4x + 7 的顶点坐标是？',
    options: [
      { id: 'a', text: '(2, 3)', weight: 1 },
      { id: 'b', text: '(-2, 3)', weight: 0 },
      { id: 'c', text: '(2, 11)', weight: 0 },
      { id: 'd', text: '(-2, 11)', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q6', topic: 'k2_函数图像与性质', difficulty: 3,
    title: '若函数 f(x) = ax² + bx + c 的图像关于直线 x = 1 对称，且过点 (0, 2) 和 (3, 5)，则 f(2) 的值为？',
    options: [
      { id: 'a', text: '4', weight: 0 },
      { id: 'b', text: '3', weight: 1 },
      { id: 'c', text: '5', weight: 0 },
      { id: 'd', text: '6', weight: 0 }
    ],
    type: 'single'
  },

  // ===== 知识点 3：三角函数 =====
  {
    id: 'q7', topic: 'k3_三角函数', difficulty: 1,
    title: 'sin²30° + cos²30° 的值为？',
    options: [
      { id: 'a', text: '1', weight: 1 },
      { id: 'b', text: '0', weight: 0 },
      { id: 'c', text: '1/2', weight: 0 },
      { id: 'd', text: '√3/2', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q8', topic: 'k3_三角函数', difficulty: 2,
    title: '在 △ABC 中，a = 3, b = 5, sinA = 1/3，则 sinB 等于？',
    options: [
      { id: 'a', text: '5/9', weight: 1 },
      { id: 'b', text: '3/5', weight: 0 },
      { id: 'c', text: '1/5', weight: 0 },
      { id: 'd', text: '1/3', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q9', topic: 'k3_三角函数', difficulty: 3,
    title: '函数 y = 2sin(2x + π/6) 的最小正周期是？',
    options: [
      { id: 'a', text: 'π', weight: 1 },
      { id: 'b', text: '2π', weight: 0 },
      { id: 'c', text: 'π/2', weight: 0 },
      { id: 'd', text: '4π', weight: 0 }
    ],
    type: 'single'
  },

  // ===== 知识点 4：数列 =====
  {
    id: 'q10', topic: 'k4_数列', difficulty: 1,
    title: '等差数列 {aₙ} 中，a₁ = 2，d = 3，则 a₁₀ 的值为？',
    options: [
      { id: 'a', text: '29', weight: 1 },
      { id: 'b', text: '32', weight: 0 },
      { id: 'c', text: '27', weight: 0 },
      { id: 'd', text: '30', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q11', topic: 'k4_数列', difficulty: 2,
    title: '等比数列 {aₙ} 中，a₂ = 6，a₄ = 54，则公比 q 为？',
    options: [
      { id: 'a', text: '3', weight: 1 },
      { id: 'b', text: '2', weight: 0 },
      { id: 'c', text: '6', weight: 0 },
      { id: 'd', text: '9', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q12', topic: 'k4_数列', difficulty: 3,
    title: '已知数列 {aₙ} 的前 n 项和 Sₙ = n² + 2n，则 a₅ 的值为？',
    options: [
      { id: 'a', text: '11', weight: 1 },
      { id: 'b', text: '15', weight: 0 },
      { id: 'c', text: '9', weight: 0 },
      { id: 'd', text: '13', weight: 0 }
    ],
    type: 'single'
  },

  // ===== 知识点 5：概率与统计 =====
  {
    id: 'q13', topic: 'k5_概率与统计', difficulty: 1,
    title: '抛掷一枚均匀硬币两次，恰好一次正面向上的概率是？',
    options: [
      { id: 'a', text: '1/2', weight: 1 },
      { id: 'b', text: '1/4', weight: 0 },
      { id: 'c', text: '3/4', weight: 0 },
      { id: 'd', text: '1/3', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q14', topic: 'k5_概率与统计', difficulty: 2,
    title: '一组数据 x₁, x₂, ..., xₙ 的方差为 4，若每个数据都乘以 3，则新数据的方差为？',
    options: [
      { id: 'a', text: '36', weight: 1 },
      { id: 'b', text: '12', weight: 0 },
      { id: 'c', text: '4', weight: 0 },
      { id: 'd', text: '6', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q15', topic: 'k5_概率与统计', difficulty: 3,
    title: '某班 40 名学生数学成绩的均值为 78 分，标准差为 8 分。若将每个人的成绩都加 5 分，则新成绩的标准差为？',
    options: [
      { id: 'a', text: '8 分', weight: 1 },
      { id: 'b', text: '13 分', weight: 0 },
      { id: 'c', text: '5 分', weight: 0 },
      { id: 'd', text: '3 分', weight: 0 }
    ],
    type: 'single'
  }
]

// ═══════════════════════════════════════════
// 页面模式
// ═══════════════════════════════════════════
type PageMode = 'loading' | 'start' | 'answering' | 'submitting' | 'report'

const pageMode = ref<PageMode>('loading')
const questions = ref<DiagnosisQuestion[]>([])
const currentIndex = ref(0)
const answers = ref<DiagnosisAnswer[]>([])
const questionStartTime = ref(0)
const selectedOption = ref<string | null>(null)
const showFeedback = ref(false)
const isCorrect = ref(false)
const diagnosisResult = ref<DiagnosisResult | null>(null)
const errorMessage = ref('')

// ECharts 实例
const radarChartRef = ref<HTMLDivElement | null>(null)
const gaugeChartRef = ref<HTMLDivElement | null>(null)
let radarChart: echarts.ECharts | null = null
let gaugeChart: echarts.ECharts | null = null

// 知识点名称映射
const KP_MAP: Record<string, string> = {
  'k1_一元二次方程': '一元二次方程',
  'k2_函数图像与性质': '函数图像与性质',
  'k3_三角函数': '三角函数',
  'k4_数列': '数列',
  'k5_概率与统计': '概率与统计'
}

// ═══════════════════════════════════════════
// 计算属性
// ═══════════════════════════════════════════
const totalQuestions = computed(() => questions.value.length)
const currentQuestion = computed<DiagnosisQuestion | null>(() => {
  return questions.value[currentIndex.value] ?? null
})
const progress = computed(() => {
  if (totalQuestions.value === 0) return 0
  return Math.round((currentIndex.value / totalQuestions.value) * 100)
})
const answeredCount = computed(() => answers.value.length)
const canGoNext = computed(() => currentIndex.value < totalQuestions.value - 1)
const isLastQuestion = computed(() => currentIndex.value >= totalQuestions.value - 1)

/** 题目难度标签颜色 */
const difficultyColor = (d: number): string => {
  const map: Record<number, string> = { 1: 'green', 2: 'cyan', 3: 'blue', 4: 'orange', 5: 'red' }
  return map[d] ?? 'default'
}
const difficultyLabel = (d: number): string => {
  const map: Record<number, string> = { 1: '基础', 2: '简单', 3: '中等', 4: '较难', 5: '困难' }
  return map[d] ?? '未知'
}

// ═══════════════════════════════════════════
// 方法
// ═══════════════════════════════════════════

/** 加载题目：优先调用 API，失败则用 Mock */
async function loadQuestions() {
  pageMode.value = 'loading'
  errorMessage.value = ''
  try {
    const data = await diagnosisApi.getQuestions()
    if (data && data.length >= 10) {
      questions.value = shuffleArray(data).slice(0, 15)
    } else {
      throw new Error('题库不足')
    }
  } catch {
    // API 不可用时使用 Mock 题库
    questions.value = shuffleArray([...MOCK_QUESTIONS]).slice(0, 15)
    console.info('[Diagnose] 使用 Mock 题库 (API 不可用)')
  }
  pageMode.value = 'start'
}

function shuffleArray<T>(arr: T[]): T[] {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

/** 开始答题 */
function startQuiz() {
  currentIndex.value = 0
  answers.value = []
  showFeedback.value = false
  selectedOption.value = null
  pageMode.value = 'answering'
  questionStartTime.value = Date.now()
}

/** 选择一个选项 */
function selectOption(optionId: string) {
  if (showFeedback.value || !currentQuestion.value) return

  selectedOption.value = optionId
  const elapsed = (Date.now() - questionStartTime.value) / 1000
  const q = currentQuestion.value
  const selectedOpt = q.options.find((o) => o.id === optionId)
  const correct = selectedOpt ? selectedOpt.weight === 1 : false

  isCorrect.value = correct

  // 记录答案
  answers.value.push({
    questionId: q.id,
    selectedOptionIds: [optionId],
    timeSpent: Math.round(elapsed * 10) / 10
  })

  // 显示反馈
  showFeedback.value = true

  // 自动跳转
  setTimeout(() => {
    goNext()
  }, 1200)
}

/** 跳转下一题 */
function goNext() {
  if (isLastQuestion.value && answers.value.length >= totalQuestions.value) {
    // 所有题目答完 → 提交
    submitAnswers()
    return
  }

  if (currentIndex.value < totalQuestions.value - 1) {
    currentIndex.value++
    selectedOption.value = null
    showFeedback.value = false
    questionStartTime.value = Date.now()
  } else if (answers.value.length >= totalQuestions.value) {
    submitAnswers()
  }
}

/** 提交答案并获取诊断结果 */
async function submitAnswers() {
  pageMode.value = 'submitting'

  try {
    const result = await diagnosisApi.submit({
      answers: answers.value,
      subject: '数学',
      grade: '高中'
    })
    diagnosisResult.value = result
  } catch {
    // 后端不可用时本地计算 Mock 结果
    diagnosisResult.value = computeMockResult()
  }

  pageMode.value = 'report'

  // 渲染图表（DOM 就绪后）
  await nextTick()
  setTimeout(() => {
    renderRadarChart()
    renderGaugeChart()
  }, 100)
}

/** 本地计算 Mock 诊断结果 */
function computeMockResult(): DiagnosisResult {
  const kpStats = new Map<string, { correct: number; total: number; totalTime: number }>()

  for (let i = 0; i < answers.value.length; i++) {
    const ans = answers.value[i]
    const q = questions.value.find((q) => q.id === ans.questionId)
    if (!q) continue

    const selectedOpt = q.options.find((o) => o.id === ans.selectedOptionIds[0])
    const correct = selectedOpt?.weight === 1

    const existing = kpStats.get(q.topic) || { correct: 0, total: 0, totalTime: 0 }
    existing.total++
    if (correct) existing.correct++
    existing.totalTime += ans.timeSpent
    kpStats.set(q.topic, existing)
  }

  // 计算掌握度
  const masteryLevels: MasteryItem[] = []
  const weakPoints: WeakPoint[] = []

  for (const [topic, stats] of kpStats.entries()) {
    const mastery = stats.total > 0 ? stats.correct / stats.total : 0
    let level: MasteryItem['level']
    if (mastery >= 0.9) level = 'excellent'
    else if (mastery >= 0.7) level = 'proficient'
    else if (mastery >= 0.4) level = 'developing'
    else level = 'weak'

    masteryLevels.push({
      knowledgePoint: KP_MAP[topic] || topic,
      mastery,
      level,
      confidence: 0.7 + Math.random() * 0.25
    })

    if (level === 'weak' || level === 'developing') {
      const reasons: Record<string, string> = {
        'k1_一元二次方程': '判别式运用不熟练，含参方程求解思路不清晰',
        'k2_函数图像与性质': '二次函数对称性与顶点坐标计算掌握不足',
        'k3_三角函数': '正弦定理灵活运用需要加强，周期判断有误',
        'k4_数列': '通项公式与前 n 项和的关系理解不够深入',
        'k5_概率与统计': '方差平移变换性质记忆混淆'
      }
      const suggestions: Record<string, string> = {
        'k1_一元二次方程': '建议从判别式的几何意义出发，结合根的分布进行专项训练',
        'k2_函数图像与性质': '建议通过描点法和函数图像变换进行操练',
        'k3_三角函数': '建议结合单位圆理解正弦定理，系统整理三角恒等式',
        'k4_数列': '建议从递推关系的角度理解 Sₙ 与 aₙ 的联系，多做转化练习',
        'k5_概率与统计': '建议对比均值与方差的线性变换规则，建立清晰记忆模型'
      }
      weakPoints.push({
        knowledgePoint: KP_MAP[topic] || topic,
        reason: reasons[topic] || `${KP_MAP[topic] || topic} 需要进一步强化`,
        severity: level === 'weak' ? 'severe' : 'moderate',
        suggestedRemediation: suggestions[topic]
      })
    }
  }

  // 按掌握度排序（低→高）
  masteryLevels.sort((a, b) => a.mastery - b.mastery)
  weakPoints.sort((a, b) => {
    const order: Record<string, number> = { severe: 0, moderate: 1, mild: 2 }
    return (order[a.severity] ?? 2) - (order[b.severity] ?? 2)
  })

  // 计算认知负荷
  const allTimes = answers.value.map((a) => a.timeSpent)
  const avgTime = allTimes.reduce((s, t) => s + t, 0) / allTimes.length
  const timeVariance = allTimes.reduce((s, t) => s + (t - avgTime) ** 2, 0) / allTimes.length

  // 错误率
  const errorCount = answers.value.filter((a, i) => {
    const q = questions.value.find((qq) => qq.id === a.questionId)
    const opt = q?.options.find((o) => o.id === a.selectedOptionIds[0])
    return opt?.weight !== 1
  }).length
  const errorRate = errorCount / answers.value.length

  const memoryLoad = Math.min(1, (avgTime / 120) * 0.7 + timeVariance / 1000)
  const attentionLoad = Math.min(1, errorRate * 0.8 + 0.15)
  const processingLoad = Math.min(1, (avgTime / 90) * 0.6 + errorRate * 0.4)
  const overall = Math.round(((memoryLoad + attentionLoad + processingLoad) / 3) * 100) / 100

  const cognitiveLoad: CognitiveLoadProfile = {
    memoryLoad: Math.round(memoryLoad * 100) / 100,
    attentionLoad: Math.round(attentionLoad * 100) / 100,
    processingLoad: Math.round(processingLoad * 100) / 100,
    overall
  }

  const overallScore = Math.round(
    masteryLevels.reduce((s, m) => s + m.mastery, 0) / masteryLevels.length * 100
  )

  const summaries: Record<string, string> = {
    excellent: '你的整体知识掌握非常扎实，认知负荷处于健康水平。建议保持当前的学习节奏，适当挑战更高难度的内容。',
    proficient: '你具备了良好的知识基础，部分知识点尚有提升空间。建议针对薄弱环节进行专项训练，进一步提升综合解题能力。',
    developing: '你的知识体系正在构建中，存在明显的薄弱环节。建议从基础概念出发，逐步加深理解，配合适量练习巩固知识点。',
    weak: '当前多个知识点掌握程度较低，认知负荷偏高。建议回归课本基础，先夯实核心概念，再逐步提升难度。'
  }

  let summaryKey: string
  if (overallScore >= 85) summaryKey = 'excellent'
  else if (overallScore >= 70) summaryKey = 'proficient'
  else if (overallScore >= 50) summaryKey = 'developing'
  else summaryKey = 'weak'

  return {
    id: `mock-${Date.now()}`,
    userId: 0,
    createdAt: new Date().toISOString(),
    subject: '数学',
    grade: '高中',
    masteryLevels,
    cognitiveLoad,
    learningStyle: overallScore >= 70 ? '视觉-逻辑型' : '循序渐进型',
    weakPoints,
    overallScore,
    summary: summaries[summaryKey]
  }
}

/** 跳转学习路径生成页面 */
function goToGeneratePath() {
  router.push({
    path: '/path',
    query: { diagnosisId: diagnosisResult.value?.id }
  })
}

/** 重新诊断 */
function restart() {
  loadQuestions().then(() => {
    pageMode.value = 'start'
  })
}

// ═══════════════════════════════════════════
// ECharts 图表
// ═══════════════════════════════════════════

function renderRadarChart() {
  if (!radarChartRef.value || !diagnosisResult.value) return

  if (radarChart) radarChart.dispose()
  radarChart = echarts.init(radarChartRef.value)

  const items = diagnosisResult.value.masteryLevels
  // 还原为原始顺序（按知识点名称排序以保持一致性）
  const sorted = [...items].sort((a, b) => a.knowledgePoint.localeCompare(b.knowledgePoint))

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'item',
      formatter: (params: unknown) => {
        const p = params as { name: string; value: number }
        const item = items.find((i) => i.knowledgePoint === p.name)
        const pct = Math.round(p.value * 100)
        return `<strong>${p.name}</strong><br/>掌握度: ${pct}%<br/>等级: ${levelText(item?.level)}`
      }
    },
    legend: {
      bottom: 0,
      data: ['掌握度'],
      textStyle: { color: '#595959', fontSize: 12 }
    },
    radar: {
      center: ['50%', '50%'],
      radius: '65%',
      indicator: sorted.map((item) => ({
        name: item.knowledgePoint,
        max: 1
      })),
      axisName: {
        color: '#262626',
        fontSize: 12,
        fontWeight: 500
      },
      splitArea: {
        areaStyle: {
          color: ['rgba(74, 144, 217, 0.05)', 'rgba(74, 144, 217, 0.1)', 'rgba(74, 144, 217, 0.05)']
        }
      },
      splitLine: { lineStyle: { color: 'rgba(74, 144, 217, 0.3)' } },
      axisLine: { lineStyle: { color: 'rgba(74, 144, 217, 0.4)' } }
    },
    series: [
      {
        name: '掌握度',
        type: 'radar',
        data: [
          {
            value: sorted.map((item) => item.mastery),
            name: '掌握度',
            areaStyle: {
              color: {
                type: 'linear',
                x: 0, y: 0, x2: 0, y2: 1,
                colorStops: [
                  { offset: 0, color: 'rgba(74, 144, 217, 0.5)' },
                  { offset: 1, color: 'rgba(74, 144, 217, 0.1)' }
                ]
              }
            },
            lineStyle: { color: '#4A90D9', width: 2 },
            itemStyle: { color: '#4A90D9' },
            symbol: 'circle',
            symbolSize: 6
          }
        ]
      }
    ]
  }

  radarChart.setOption(option)
}

function renderGaugeChart() {
  if (!gaugeChartRef.value || !diagnosisResult.value) return

  if (gaugeChart) gaugeChart.dispose()
  gaugeChart = echarts.init(gaugeChartRef.value)

  const load = diagnosisResult.value.cognitiveLoad.overall
  const loadPct = Math.round(load * 100)

  let colorStops: [number, string][]
  if (load < 0.35) {
    colorStops = [
      [0.3, '#52c41a'],
      [0.7, '#faad14'],
      [1, '#ff4d4f']
    ]
  } else if (load < 0.65) {
    colorStops = [
      [0.3, '#52c41a'],
      [0.7, '#faad14'],
      [1, '#ff4d4f']
    ]
  } else {
    colorStops = [
      [0.3, '#faad14'],
      [0.7, '#ff4d4f'],
      [1, '#ff4d4f']
    ]
  }

  const option: echarts.EChartsOption = {
    series: [
      {
        type: 'gauge',
        startAngle: 210,
        endAngle: -30,
        center: ['50%', '55%'],
        radius: '90%',
        min: 0,
        max: 100,
        splitNumber: 10,
        axisLine: {
          show: true,
          lineStyle: {
            width: 18,
            color: colorStops
          }
        },
        pointer: {
          icon: 'path://M12.8,0.7l12,40.1H0.7L12.8,0.7z',
          length: '70%',
          width: 6,
          offsetCenter: [0, '-10%'],
          itemStyle: {
            color: 'auto'
          }
        },
        axisTick: { distance: -18, length: 6, lineStyle: { width: 1, color: '#999' } },
        splitLine: { distance: -22, length: 18, lineStyle: { width: 2, color: '#999' } },
        axisLabel: {
          color: '#595959',
          distance: 25,
          fontSize: 11,
          formatter: (value: number) => `${value}%`
        },
        anchor: { show: true, showAbove: true, size: 18, itemStyle: { borderWidth: 2 } },
        title: { show: false },
        detail: {
          valueAnimation: true,
          fontSize: 28,
          fontWeight: 'bold',
          offsetCenter: [0, '65%'],
          formatter: '{value}%',
          color: '#262626'
        },
        data: [{ value: loadPct, name: '认知负荷' }]
      }
    ]
  }

  gaugeChart.setOption(option)
}

function levelText(level?: MasteryItem['level']): string {
  const map: Record<string, string> = {
    excellent: '优秀',
    proficient: '熟练',
    developing: '发展中',
    weak: '薄弱'
  }
  return map[level ?? ''] ?? '未知'
}

function loadLevelText(load: number): { text: string; color: string } {
  if (load < 0.35) return { text: '轻松', color: '#52c41a' }
  if (load < 0.65) return { text: '适中', color: '#faad14' }
  return { text: '较高', color: '#ff4d4f' }
}

function severityColor(s: WeakPoint['severity']): string {
  const map: Record<string, string> = { severe: '#ff4d4f', moderate: '#faad14', mild: '#52c41a' }
  return map[s] ?? '#8c8c8c'
}
function severityText(s: WeakPoint['severity']): string {
  const map: Record<string, string> = { severe: '严重', moderate: '中等', mild: '轻微' }
  return map[s] ?? '未知'
}

// ═══════════════════════════════════════════
// 响应式处理
// ═══════════════════════════════════════════
function handleResize() {
  radarChart?.resize()
  gaugeChart?.resize()
}

// ═══════════════════════════════════════════
// 生命周期
// ═══════════════════════════════════════════
onMounted(() => {
  loadQuestions()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  radarChart?.dispose()
  gaugeChart?.dispose()
})

// 监听报告模式变化，重新渲染图表
watch(pageMode, (mode) => {
  if (mode === 'report') {
    nextTick(() => {
      setTimeout(() => {
        renderRadarChart()
        renderGaugeChart()
      }, 150)
    })
  }
})
</script>

<template>
  <div class="diagnose-page">
    <!-- ═══════ 加载态 ═══════ -->
    <div v-if="pageMode === 'loading'" class="diagnose-loading">
      <a-spin size="large" tip="正在加载题库..." />
    </div>

    <!-- ═══════ 开始页面 ═══════ -->
    <div v-else-if="pageMode === 'start'" class="diagnose-start">
      <a-card class="start-card" :bordered="false">
        <div class="start-header">
          <div class="start-icon-wrapper">
            <ExperimentOutlined class="start-icon" />
          </div>
          <h1 class="start-title">认知诊断测验</h1>
          <p class="start-subtitle">AI 驱动的知识点诊断，精准定位学习薄弱环节</p>
        </div>

        <a-divider />

        <div class="start-info">
          <div class="info-grid">
            <div class="info-item">
              <BookOutlined class="info-icon" />
              <div>
                <div class="info-label">题目数量</div>
                <div class="info-value">{{ totalQuestions }} 道题</div>
              </div>
            </div>
            <div class="info-item">
              <ClockCircleOutlined class="info-icon" />
              <div>
                <div class="info-label">预计用时</div>
                <div class="info-value">10-15 分钟</div>
              </div>
            </div>
            <div class="info-item">
              <AimOutlined class="info-icon" />
              <div>
                <div class="info-label">诊断维度</div>
                <div class="info-value">知识点掌握 + 认知负荷</div>
              </div>
            </div>
          </div>
        </div>

        <div class="start-tips">
          <a-alert type="info" :show-icon="false">
            <template #message>
              <div class="tips-content">
                <BulbOutlined style="color: #4A90D9" />
                <span>每题作答后自动进入下一题，请认真思考后选择。系统将根据你的答题时间和正确率综合评估学习状态。</span>
              </div>
            </template>
          </a-alert>
        </div>

        <div class="start-actions">
          <a-button type="primary" size="large" @click="startQuiz" class="start-btn">
            <PlayCircleOutlined />
            开始诊断
          </a-button>
          <a-button size="large" @click="router.back()">返回</a-button>
        </div>
      </a-card>
    </div>

    <!-- ═══════ 答题页面 ═══════ -->
    <div v-else-if="pageMode === 'answering'" class="diagnose-quiz">
      <!-- 顶部进度条 -->
      <div class="quiz-header">
        <div class="quiz-progress-info">
          <span class="progress-text">
            第 <strong>{{ currentIndex + 1 }}</strong> / {{ totalQuestions }} 题
          </span>
          <span class="answered-text">
            已答 {{ answeredCount }} 题
          </span>
        </div>
        <a-progress
          :percent="progress"
          :show-info="false"
          :stroke-color="{ from: '#4A90D9', to: '#E8D5B7' }"
          :stroke-width="8"
          class="quiz-progress-bar"
        />
      </div>

      <!-- 题目卡片 -->
      <transition name="slide-fade" mode="out-in">
        <a-card v-if="currentQuestion" :key="currentQuestion.id" class="question-card" :bordered="false">
          <!-- 题目头部标签 -->
          <div class="question-meta">
            <a-tag :color="difficultyColor(currentQuestion.difficulty)" class="difficulty-tag">
              {{ difficultyLabel(currentQuestion.difficulty) }}
            </a-tag>
            <a-tag color="#E8D5B7" class="topic-tag" :style="{ color: '#7a5a30' }">
              {{ KP_MAP[currentQuestion.topic] || currentQuestion.topic }}
            </a-tag>
          </div>

          <!-- 题目内容 -->
          <div class="question-body">
            <h3 class="question-title">{{ currentQuestion.title }}</h3>
          </div>

          <!-- 选项列表 -->
          <div class="options-list">
            <div
              v-for="(opt, idx) in currentQuestion.options"
              :key="opt.id"
              class="option-item"
              :class="{
                'option-selected': selectedOption === opt.id && !showFeedback,
                'option-correct': showFeedback && opt.weight === 1,
                'option-wrong': showFeedback && selectedOption === opt.id && opt.weight !== 1,
                'option-dimmed': showFeedback && selectedOption !== opt.id && opt.weight !== 1
              }"
              @click="selectOption(opt.id)"
            >
              <span class="option-label">{{ ['A', 'B', 'C', 'D'][idx] }}</span>
              <span class="option-text">{{ opt.text }}</span>
              <span v-if="showFeedback && opt.weight === 1" class="option-icon-correct">
                <CheckCircleOutlined />
              </span>
              <span v-else-if="showFeedback && selectedOption === opt.id && opt.weight !== 1" class="option-icon-wrong">
                <CloseCircleOutlined />
              </span>
            </div>
          </div>

          <!-- 答题反馈 -->
          <transition name="feedback-fade">
            <div v-if="showFeedback" class="question-feedback">
              <a-alert
                :type="isCorrect ? 'success' : 'error'"
                :message="isCorrect ? '回答正确！' : '回答错误'"
                :show-icon="false"
              >
                <template #icon>
                  <CheckCircleOutlined v-if="isCorrect" />
                  <CloseCircleOutlined v-else />
                </template>
              </a-alert>
            </div>
          </transition>
        </a-card>
      </transition>

      <!-- 底部操作栏 -->
      <div class="quiz-footer">
        <a-button v-if="currentIndex > 0 && !showFeedback" @click="currentIndex--; selectedOption = null">
          上一题
        </a-button>
        <div class="footer-spacer" />
        <span v-if="isLastQuestion && answers.value.length >= totalQuestions" class="quiz-ready-text">
          <CheckCircleOutlined style="color: #52c41a" />
          全部作答完成，即将提交...
        </span>
      </div>
    </div>

    <!-- ═══════ 提交中 ═══════ -->
    <div v-else-if="pageMode === 'submitting'" class="diagnose-submitting">
      <a-spin size="large" />
      <div class="submitting-text">AI 正在分析你的答题数据，生成诊断报告...</div>
      <div class="submitting-animation">
        <div class="dot-pulse">
          <span class="dot"></span>
          <span class="dot"></span>
          <span class="dot"></span>
        </div>
      </div>
    </div>

    <!-- ═══════ 诊断报告页面 ═══════ -->
    <div v-else-if="pageMode === 'report' && diagnosisResult" class="diagnose-report">
      <!-- 报告头部 -->
      <div class="report-header">
        <div class="report-header-badge">
          <TrophyOutlined />
        </div>
        <h1 class="report-title">诊断报告</h1>
        <p class="report-meta">
          {{ diagnosisResult.subject }} · {{ diagnosisResult.grade }} ·
          完成时间 {{ new Date(diagnosisResult.createdAt).toLocaleString('zh-CN') }}
        </p>
        <div class="report-score-badge">
          <span class="score-number">{{ diagnosisResult.overallScore }}</span>
          <span class="score-label">综合评分</span>
        </div>
      </div>

      <!-- 📊 图表行 -->
      <a-row :gutter="16" class="report-charts-row">
        <!-- 知识掌握度雷达图 -->
        <a-col :xs="24" :lg="14">
          <a-card class="chart-card" :bordered="false" title="知识点掌握度">
            <template #extra>
              <a-tag color="#4A90D9">雷达图</a-tag>
            </template>
            <div ref="radarChartRef" class="chart-container"></div>
          </a-card>
        </a-col>

        <!-- 认知负荷仪表盘 -->
        <a-col :xs="24" :lg="10">
          <a-card class="chart-card" :bordered="false" title="认知负荷指数">
            <template #extra>
              <a-tag
                :color="loadLevelText(diagnosisResult.cognitiveLoad.overall).color"
              >
                {{ loadLevelText(diagnosisResult.cognitiveLoad.overall).text }}
              </a-tag>
            </template>
            <div ref="gaugeChartRef" class="chart-container gauge-container"></div>
          </a-card>
        </a-col>
      </a-row>

      <!-- 认知负荷细节 -->
      <a-row :gutter="16" class="load-detail-row">
        <a-col :xs="24" :sm="8">
          <div class="load-detail-card">
            <div class="load-detail-header">
              <ThunderboltOutlined />
              记忆负荷
            </div>
            <a-progress
              :percent="Math.round(diagnosisResult.cognitiveLoad.memoryLoad * 100)"
              :stroke-color="diagnosisResult.cognitiveLoad.memoryLoad > 0.6 ? '#ff4d4f' : '#4A90D9'"
              :size="'small'"
            />
          </div>
        </a-col>
        <a-col :xs="24" :sm="8">
          <div class="load-detail-card">
            <div class="load-detail-header">
              <AimOutlined />
              注意力负荷
            </div>
            <a-progress
              :percent="Math.round(diagnosisResult.cognitiveLoad.attentionLoad * 100)"
              :stroke-color="diagnosisResult.cognitiveLoad.attentionLoad > 0.6 ? '#ff4d4f' : '#4A90D9'"
              :size="'small'"
            />
          </div>
        </a-col>
        <a-col :xs="24" :sm="8">
          <div class="load-detail-card">
            <div class="load-detail-header">
              <ExperimentOutlined />
              加工负荷
            </div>
            <a-progress
              :percent="Math.round(diagnosisResult.cognitiveLoad.processingLoad * 100)"
              :stroke-color="diagnosisResult.cognitiveLoad.processingLoad > 0.6 ? '#ff4d4f' : '#4A90D9'"
              :size="'small'"
            />
          </div>
        </a-col>
      </a-row>

      <!-- 📋 掌握度详情 + 薄弱点 -->
      <a-row :gutter="16" class="report-detail-row">
        <!-- 知识点掌握度列表 -->
        <a-col :xs="24" :lg="12">
          <a-card class="detail-card" :bordered="false" title="各知识点掌握详情">
            <template #extra>
              <a-tag color="#E8D5B7" :style="{ color: '#7a5a30' }">按掌握度排序</a-tag>
            </template>
            <div class="mastery-list">
              <div
                v-for="(item, idx) in diagnosisResult.masteryLevels"
                :key="idx"
                class="mastery-item"
              >
                <div class="mastery-item-header">
                  <span class="mastery-name">{{ item.knowledgePoint }}</span>
                  <a-tag :color="item.level === 'excellent' ? 'green' : item.level === 'proficient' ? 'blue' : item.level === 'developing' ? 'orange' : 'red'">
                    {{ levelText(item.level) }}
                  </a-tag>
                </div>
                <a-progress
                  :percent="Math.round(item.mastery * 100)"
                  :stroke-color="item.mastery >= 0.7 ? '#52c41a' : item.mastery >= 0.4 ? '#faad14' : '#ff4d4f'"
                  :size="'small'"
                />
                <div class="mastery-confidence">
                  置信度 {{ Math.round(item.confidence * 100) }}%
                </div>
              </div>
            </div>
          </a-card>
        </a-col>

        <!-- 薄弱知识点 -->
        <a-col :xs="24" :lg="12">
          <a-card class="detail-card weak-point-card" :bordered="false">
            <template #title>
              <span class="weak-point-title">
                <WarningOutlined style="color: #faad14; margin-right: 6px" />
                薄弱知识点
              </span>
            </template>
            <template #extra>
              <a-tag v-if="diagnosisResult.weakPoints.length === 0" color="green">暂无薄弱点</a-tag>
              <a-tag v-else color="orange">{{ diagnosisResult.weakPoints.length }} 个薄弱点</a-tag>
            </template>

            <div v-if="diagnosisResult.weakPoints.length === 0" class="no-weak-points">
              <CheckCircleOutlined style="font-size: 36px; color: #52c41a" />
              <p>恭喜！所有知识点都达到了良好水平</p>
            </div>

            <div v-else class="weak-point-list">
              <div
                v-for="(wp, idx) in diagnosisResult.weakPoints"
                :key="idx"
                class="weak-point-item"
              >
                <div class="wp-header">
                  <span class="wp-name">
                    <a-tag :color="severityColor(wp.severity)" class="severity-tag">
                      {{ severityText(wp.severity) }}
                    </a-tag>
                    {{ wp.knowledgePoint }}
                  </span>
                </div>
                <div class="wp-reason">
                  <BulbOutlined class="wp-reason-icon" />
                  {{ wp.reason }}
                </div>
                <div v-if="wp.suggestedRemediation" class="wp-suggestion">
                  <BookOutlined class="wp-suggestion-icon" />
                  {{ wp.suggestedRemediation }}
                </div>
              </div>
            </div>
          </a-card>
        </a-col>
      </a-row>

      <!-- 📝 AI 诊断摘要 -->
      <a-card class="summary-card" :bordered="false" title="AI 诊断摘要">
        <template #extra>
          <span class="learning-style-tag">{{ diagnosisResult.learningStyle }}</span>
        </template>
        <p class="summary-text">{{ diagnosisResult.summary }}</p>
      </a-card>

      <!-- 🚀 操作按钮 -->
      <div class="report-actions">
        <a-button type="primary" size="large" class="generate-path-btn" @click="goToGeneratePath">
          <RocketOutlined />
          生成学习路径
        </a-button>
        <a-button size="large" @click="restart">
          <ReloadOutlined />
          重新诊断
        </a-button>
        <a-button size="large" @click="router.push('/home')">
          返回首页
        </a-button>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
export default {
  components: {
    ExperimentOutlined,
    ClockCircleOutlined,
    CheckCircleOutlined,
    CloseCircleOutlined,
    ThunderboltOutlined,
    BulbOutlined,
    RocketOutlined,
    TrophyOutlined,
    ArrowRightOutlined,
    ReloadOutlined,
    BarChartOutlined,
    WarningOutlined,
    AimOutlined,
    PlayCircleOutlined,
    BookOutlined
  }
}
</script>

<style scoped>
/* ═══════════════════════════════════════════
   Diagnose Page — 整体容器
   ═══════════════════════════════════════════ */
.diagnose-page {
  max-width: 860px;
  margin: 0 auto;
  padding: 0 12px;
}

/* ═══════════════════════════════════════════
   加载态
   ═══════════════════════════════════════════ */
.diagnose-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 50vh;
}

/* ═══════════════════════════════════════════
   开始页面
   ═══════════════════════════════════════════ */
.start-card {
  margin-top: 24px;
  border-radius: 16px;
  box-shadow: 0 2px 16px rgba(0, 0, 0, 0.06);
}

.start-header {
  text-align: center;
  padding: 16px 0 8px;
}

.start-icon-wrapper {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: linear-gradient(135deg, #E8D5B7 0%, #f5e6cc 100%);
  margin-bottom: 16px;
}

.start-icon {
  font-size: 36px;
  color: #4A6CF7;
}

.start-title {
  font-size: 26px;
  font-weight: 700;
  color: #F8FAFC;
  margin: 0 0 8px;
}

.start-subtitle {
  font-size: 15px;
  color: #94A3B8;
  margin: 0;
}

.start-info {
  padding: 12px 0;
}

.info-grid {
  display: flex;
  justify-content: center;
  gap: 40px;
  flex-wrap: wrap;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.info-icon {
  font-size: 24px;
  color: #4A6CF7;
  opacity: 0.8;
}

.info-label {
  font-size: 12px;
  color: #94A3B8;
}

.info-value {
  font-size: 14px;
  font-weight: 600;
  color: #E2E8F0;
}

.start-tips {
  margin: 12px 0;
}

.tips-content {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #D4A373;
  background: rgba(212, 163, 115, 0.08);
  padding: 10px 16px;
  border-radius: 8px;
  border: 1px solid rgba(212, 163, 115, 0.15);
}

.start-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 24px;
}

.start-btn {
  min-width: 160px;
  height: 44px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 10px;
  background: linear-gradient(135deg, #D4A373 0%, #C08B5C 100%);
  border: none;
  color: #0A0D14;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ═══════════════════════════════════════════
   答题页面
   ═══════════════════════════════════════════ */
.quiz-header {
  margin: 16px 0 20px;
}

.quiz-progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.progress-text {
  font-size: 14px;
  color: #94A3B8;
}

.progress-text strong {
  color: #F8FAFC;
  font-size: 16px;
}

.answered-text {
  font-size: 13px;
  color: #94A3B8;
}

.quiz-progress-bar {
  line-height: 1;
}

/* 题目卡片 */
.question-card {
  border-radius: 16px;
  box-shadow: 0 2px 16px rgba(0, 0, 0, 0.3);
  min-height: 320px;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.question-meta {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.difficulty-tag {
  font-size: 12px;
  border-radius: 6px;
}

.topic-tag {
  font-size: 12px;
  border-radius: 6px;
  background: rgba(212, 163, 115, 0.12) !important;
  border-color: rgba(212, 163, 115, 0.25) !important;
}

.question-body {
  margin-bottom: 28px;
}

.question-title {
  font-size: 18px;
  font-weight: 600;
  color: #F8FAFC;
  line-height: 1.6;
  margin: 0;
}

/* 选项列表 — 毛玻璃芯片 */
.options-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.option-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.25s ease;
  position: relative;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(10px);
}

.option-item:hover:not(.option-correct):not(.option-wrong):not(.option-dimmed) {
  border-color: rgba(74, 108, 247, 0.40);
  background: rgba(74, 108, 247, 0.08);
  transform: translateX(4px);
}

.option-selected {
  border-color: #D4A373;
  background: rgba(212, 163, 115, 0.12);
}

.option-correct {
  border-color: #34D399;
  background: rgba(52, 211, 153, 0.08);
  cursor: default;
}

.option-wrong {
  border-color: #F87171;
  background: rgba(248, 113, 113, 0.08);
  cursor: default;
}

.option-dimmed {
  opacity: 0.35;
  cursor: default;
}

.option-label {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  font-weight: 700;
  font-size: 14px;
  color: #94A3B8;
  flex-shrink: 0;
  transition: all 0.25s;
}

.option-selected .option-label {
  background: #D4A373;
  color: #0A0D14;
}

.option-correct .option-label {
  background: #34D399;
  color: #0A0D14;
}

.option-wrong .option-label {
  background: #F87171;
  color: #fff;
}

.option-text {
  flex: 1;
  font-size: 15px;
  color: #E2E8F0;
  line-height: 1.5;
}

.option-icon-correct {
  color: #34D399;
  font-size: 20px;
}

.option-icon-wrong {
  color: #F87171;
  font-size: 20px;
}

/* 答题反馈 */
.question-feedback {
  margin-top: 20px;
}

/* 底部操作栏 */
.quiz-footer {
  display: flex;
  align-items: center;
  margin-top: 20px;
  padding-bottom: 40px;
}

.footer-spacer {
  flex: 1;
}

.quiz-ready-text {
  font-size: 14px;
  color: #52c41a;
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ═══════════════════════════════════════════
   提交中
   ═══════════════════════════════════════════ */
.diagnose-submitting {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 50vh;
  gap: 16px;
}

.submitting-text {
  font-size: 15px;
  color: #94A3B8;
}

.dot-pulse {
  display: flex;
  gap: 6px;
}

.dot-pulse .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4A90D9;
  animation: dotPulse 1.4s infinite ease-in-out both;
}

.dot-pulse .dot:nth-child(1) { animation-delay: -0.32s; }
.dot-pulse .dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes dotPulse {
  0%, 80%, 100% { transform: scale(0); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* ═══════════════════════════════════════════
   诊断报告页面
   ═══════════════════════════════════════════ */
.diagnose-report {
  padding-bottom: 40px;
}

/* 报告头部 */
.report-header {
  text-align: center;
  padding: 36px 20px 28px;
  position: relative;
}

.report-header-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4A6CF7 0%, #1D4ED8 100%);
  color: #fff;
  font-size: 30px;
  margin-bottom: 12px;
}

.report-title {
  font-size: 26px;
  font-weight: 700;
  color: #F8FAFC;
  margin: 0 0 6px;
}

.report-meta {
  font-size: 13px;
  color: #94A3B8;
  margin: 0;
}

.report-score-badge {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  margin-top: 16px;
  padding: 12px 28px;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.score-number {
  font-size: 36px;
  font-weight: 800;
  color: #D4A373;
  line-height: 1;
}

.score-label {
  font-size: 12px;
  color: #94A3B8;
  margin-top: 4px;
}

/* 图表行 */
.report-charts-row {
  margin-bottom: 16px;
}

.chart-card {
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  height: 100%;
}

.chart-card :deep(.ant-card-head) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.chart-card :deep(.ant-card-head-title) {
  font-weight: 600;
  font-size: 15px;
}

.chart-container {
  width: 100%;
  height: 360px;
}

.gauge-container {
  height: 340px;
}

/* 认知负荷细节 */
.load-detail-row {
  margin-bottom: 16px;
}

.load-detail-card {
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px);
  border-radius: 12px;
  padding: 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  margin-bottom: 12px;
}

.load-detail-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #94A3B8;
  margin-bottom: 10px;
}

/* 详情行 */
.report-detail-row {
  margin-bottom: 16px;
}

.detail-card {
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
  height: 100%;
  margin-bottom: 12px;
}

.detail-card :deep(.ant-card-head-title) {
  font-weight: 600;
  font-size: 15px;
}

/* 掌握度列表 */
.mastery-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.mastery-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.mastery-name {
  font-size: 14px;
  font-weight: 500;
  color: #E2E8F0;
}

.mastery-confidence {
  font-size: 11px;
  color: #94A3B8;
  margin-top: 4px;
  text-align: right;
}

/* 薄弱点 */
.weak-point-title {
  color: #F8FAFC;
}

.weak-point-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.no-weak-points {
  text-align: center;
  padding: 32px 0;
}

.no-weak-points p {
  font-size: 14px;
  color: #94A3B8;
  margin-top: 8px;
}

.weak-point-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.weak-point-item {
  padding: 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.wp-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.wp-name {
  font-size: 14px;
  font-weight: 600;
  color: #E2E8F0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.severity-tag {
  font-size: 11px;
  border-radius: 4px;
  line-height: 1;
}

.wp-reason {
  font-size: 13px;
  color: #94A3B8;
  line-height: 1.5;
  padding-left: 22px;
  position: relative;
}

.wp-reason-icon {
  font-size: 13px;
  color: #4A90D9;
  position: absolute;
  left: 0;
  top: 2px;
}

.wp-suggestion {
  font-size: 12px;
  color: #7a5a30;
  background: rgba(232, 213, 183, 0.3);
  padding: 8px 12px;
  border-radius: 8px;
  margin-top: 8px;
  line-height: 1.5;
  padding-left: 22px;
  position: relative;
}

.wp-suggestion-icon {
  font-size: 13px;
  color: #E8D5B7;
  position: absolute;
  left: 12px;
  top: 10px;
}

/* AI 摘要 */
.summary-card {
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
  margin-bottom: 24px;
  border-left: 4px solid #4A90D9;
}

.summary-card :deep(.ant-card-head-title) {
  font-weight: 600;
  font-size: 15px;
}

.learning-style-tag {
  font-size: 12px;
  color: #4A90D9;
  font-weight: 500;
}

.summary-text {
  font-size: 14px;
  color: #94A3B8;
  line-height: 1.8;
  margin: 0;
}

/* 操作按钮 */
.report-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.generate-path-btn {
  min-width: 180px;
  height: 44px;
  font-size: 15px;
  font-weight: 600;
  border-radius: 10px;
  background: linear-gradient(135deg, #4A90D9 0%, #3a7bc8 100%);
  border: none;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ═══════════════════════════════════════════
   动画
   ═══════════════════════════════════════════ */
.slide-fade-enter-active {
  transition: all 0.35s ease-out;
}

.slide-fade-leave-active {
  transition: all 0.2s ease-in;
}

.slide-fade-enter-from {
  transform: translateX(30px);
  opacity: 0;
}

.slide-fade-leave-to {
  transform: translateX(-20px);
  opacity: 0;
}

.feedback-fade-enter-active {
  transition: all 0.3s ease-out;
}

.feedback-fade-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}

/* ═══════════════════════════════════════════
   响应式
   ═══════════════════════════════════════════ */
@media (max-width: 768px) {
  .diagnose-page {
    padding: 0 4px;
  }

  .info-grid {
    flex-direction: column;
    gap: 16px;
    align-items: flex-start;
    padding-left: 20px;
  }

  .chart-container {
    height: 280px;
  }

  .gauge-container {
    height: 260px;
  }

  .report-header {
    padding: 24px 12px 20px;
  }

  .report-title {
    font-size: 22px;
  }

  .report-actions {
    flex-direction: column;
    align-items: center;
  }

  .question-title {
    font-size: 16px;
  }
}
</style>
