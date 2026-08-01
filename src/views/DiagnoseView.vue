<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
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
// Mock 题库（15 道题，5 个 AI 通识知识点，每个知识点 3 题）
// ═══════════════════════════════════════════
const MOCK_QUESTIONS: DiagnosisQuestion[] = [
  // ===== 知识点 1：人工智能基础概念 =====
  {
    id: 'q1',
    topic: 'k1_人工智能基础概念',
    difficulty: 1,
    title: '人工智能（AI）这一概念诞生于哪一年的什么会议？',
    options: [
      { id: 'a', text: '1956年 达特茅斯会议', weight: 1 },
      { id: 'b', text: '1960年 纽约会议', weight: 0 },
      { id: 'c', text: '1972年 斯德哥尔摩会议', weight: 0 },
      { id: 'd', text: '1980年 东京会议', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q2',
    topic: 'k1_人工智能基础概念',
    difficulty: 2,
    title: '根据课程内容，人工智能最本质的属性是什么？',
    options: [
      { id: 'a', text: '意识与自由意志', weight: 0 },
      { id: 'b', text: '能力（学习、判断、理解等大脑能力）', weight: 1 },
      { id: 'c', text: '情感与创造力', weight: 0 },
      { id: 'd', text: '自我复制与进化', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q3',
    topic: 'k1_人工智能基础概念',
    difficulty: 3,
    title: '下列哪位人物提出了"图灵测试"，为判断机器是否具有智能设立了标准？',
    options: [
      { id: 'a', text: '阿兰·图灵 (Alan Turing)', weight: 1 },
      { id: 'b', text: '杰弗里·辛顿 (Geoffrey Hinton)', weight: 0 },
      { id: 'c', text: '约翰·麦卡锡 (John McCarthy)', weight: 0 },
      { id: 'd', text: '诺姆·乔姆斯基 (Noam Chomsky)', weight: 0 }
    ],
    type: 'single'
  },

  // ===== 知识点 2：机器学习基础 =====
  {
    id: 'q4',
    topic: 'k2_机器学习基础',
    difficulty: 1,
    title: '机器学习的三大范式不包括以下哪个？',
    options: [
      { id: 'a', text: '监督学习', weight: 0 },
      { id: 'b', text: '无监督学习', weight: 0 },
      { id: 'c', text: '知识驱动学习', weight: 1 },
      { id: 'd', text: '强化学习', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q5',
    topic: 'k2_机器学习基础',
    difficulty: 2,
    title: '模型在训练集上表现很好但在测试集上表现较差，这种现象叫什么？',
    options: [
      { id: 'a', text: '过拟合 (Overfitting)', weight: 1 },
      { id: 'b', text: '欠拟合 (Underfitting)', weight: 0 },
      { id: 'c', text: '梯度消失', weight: 0 },
      { id: 'd', text: '数据泄露', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q6',
    topic: 'k2_机器学习基础',
    difficulty: 3,
    title: 'K-means 聚类算法属于哪种学习范式？',
    options: [
      { id: 'a', text: '监督学习', weight: 0 },
      { id: 'b', text: '无监督学习', weight: 1 },
      { id: 'c', text: '半监督学习', weight: 0 },
      { id: 'd', text: '强化学习', weight: 0 }
    ],
    type: 'single'
  },

  // ===== 知识点 3：深度学习与神经网络 =====
  {
    id: 'q7',
    topic: 'k3_深度学习与神经网络',
    difficulty: 1,
    title: '神经网络的基本计算单元是什么？',
    options: [
      { id: 'a', text: '感知机 / 神经元', weight: 1 },
      { id: 'b', text: '决策树', weight: 0 },
      { id: 'c', text: '支持向量', weight: 0 },
      { id: 'd', text: '聚类中心', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q8',
    topic: 'k3_深度学习与神经网络',
    difficulty: 2,
    title: '以下哪个激活函数解决了梯度消失问题且计算效率高？',
    options: [
      { id: 'a', text: 'ReLU (Rectified Linear Unit)', weight: 1 },
      { id: 'b', text: 'Sigmoid', weight: 0 },
      { id: 'c', text: 'Tanh', weight: 0 },
      { id: 'd', text: 'Softmax', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q9',
    topic: 'k3_深度学习与神经网络',
    difficulty: 3,
    title: 'CNN（卷积神经网络）中，池化层（Pooling）的主要作用是什么？',
    options: [
      { id: 'a', text: '增加特征数量', weight: 0 },
      { id: 'b', text: '降维并保留主要特征，减少计算量', weight: 1 },
      { id: 'c', text: '学习非线性映射', weight: 0 },
      { id: 'd', text: '将特征图转换为一维向量', weight: 0 }
    ],
    type: 'single'
  },

  // ===== 知识点 4：自然语言处理与大模型 =====
  {
    id: 'q10',
    topic: 'k4_自然语言处理与大模型',
    difficulty: 1,
    title: 'Transformer 架构的核心机制是什么？',
    options: [
      { id: 'a', text: '自注意力机制 (Self-Attention)', weight: 1 },
      { id: 'b', text: '循环连接 (Recurrent Connection)', weight: 0 },
      { id: 'c', text: '卷积核 (Convolution Kernel)', weight: 0 },
      { id: 'd', text: '全连接层 (Fully Connected Layer)', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q11',
    topic: 'k4_自然语言处理与大模型',
    difficulty: 2,
    title: 'BERT 模型与 GPT 模型在训练方式上的主要区别是什么？',
    options: [
      { id: 'a', text: 'BERT是双向编码器，GPT是单向自回归解码器', weight: 1 },
      { id: 'b', text: 'BERT使用CNN，GPT使用RNN', weight: 0 },
      { id: 'c', text: '两者训练方式完全相同', weight: 0 },
      { id: 'd', text: 'BERT不需要预训练', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q12',
    topic: 'k4_自然语言处理与大模型',
    difficulty: 3,
    title: '以下哪项技术用于对齐大语言模型与人类价值观？',
    options: [
      { id: 'a', text: 'RLHF (基于人类反馈的强化学习)', weight: 1 },
      { id: 'b', text: '数据增强', weight: 0 },
      { id: 'c', text: 'Dropout', weight: 0 },
      { id: 'd', text: 'Batch Normalization', weight: 0 }
    ],
    type: 'single'
  },

  // ===== 知识点 5：AI伦理与前沿应用 =====
  {
    id: 'q13',
    topic: 'k5_AI伦理与前沿应用',
    difficulty: 1,
    title: '以下哪项是AI伦理的核心原则之一？',
    options: [
      { id: 'a', text: '公平性 (Fairness)', weight: 1 },
      { id: 'b', text: '最大化利润', weight: 0 },
      { id: 'c', text: '最小化代码量', weight: 0 },
      { id: 'd', text: '追求最高准确率', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q14',
    topic: 'k5_AI伦理与前沿应用',
    difficulty: 2,
    title: 'Stable Diffusion 和 DALL-E 属于哪种AI技术？',
    options: [
      { id: 'a', text: '扩散模型 / 文生图模型', weight: 1 },
      { id: 'b', text: '语音识别模型', weight: 0 },
      { id: 'c', text: '推荐系统模型', weight: 0 },
      { id: 'd', text: '时间序列预测模型', weight: 0 }
    ],
    type: 'single'
  },
  {
    id: 'q15',
    topic: 'k5_AI伦理与前沿应用',
    difficulty: 3,
    title: '联邦学习 (Federated Learning) 的核心优势是什么？',
    options: [
      { id: 'a', text: '保护数据隐私，数据不出本地即可协同训练模型', weight: 1 },
      { id: 'b', text: '大幅减少模型参数量', weight: 0 },
      { id: 'c', text: '不需要任何标注数据', weight: 0 },
      { id: 'd', text: '训练速度比集中式快 100 倍', weight: 0 }
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
  k1_人工智能基础概念: '人工智能基础概念',
  k2_机器学习基础: '机器学习基础',
  k3_深度学习与神经网络: '深度学习与神经网络',
  k4_自然语言处理与大模型: '自然语言处理与大模型',
  k5_AI伦理与前沿应用: 'AI伦理与前沿应用'
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
    // API 返回 QuestionsResponse { questions: [...], total, subject, estimated_duration_min }
    const qList = data.questions
    if (Array.isArray(qList) && qList.length >= 10) {
      questions.value = shuffleArray(qList).slice(0, 15)
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
    const j = Math.floor(Math.random() * (i + 1))
    const tmp = a[j]!
    a[j] = a[i]!
    a[i] = tmp
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

/** 返回上一题（模板中不能写多条语句，抽成方法） */
function goPrevQuestion() {
  if (currentIndex.value <= 0) return
  currentIndex.value--
  selectedOption.value = null
  showFeedback.value = false
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
    selectedOption: optionId,
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
      subject: '人工智能导论',
      grade: '大学'
    })
    diagnosisResult.value = result
  } catch {
    // 后端不可用时本地计算 Mock 结果
    try {
      diagnosisResult.value = computeMockResult()
    } catch (mockError) {
      console.error('Mock 诊断计算失败:', mockError)
      diagnosisResult.value = createFallbackResult()
    }
  }

  pageMode.value = 'report'

  // 渲染图表（DOM 就绪后）
  await nextTick()
  setTimeout(() => {
    try {
      renderRadarChart()
      renderGaugeChart()
    } catch (chartError) {
      console.error('图表渲染失败:', chartError)
    }
  }, 100)
}

/** 本地计算 Mock 诊断结果 */
function computeMockResult(): DiagnosisResult {
  const kpStats = new Map<string, { correct: number; total: number; totalTime: number }>()

  for (let i = 0; i < answers.value.length; i++) {
    const ans = answers.value[i]!
    const q = questions.value.find((q) => q.id === ans.questionId)
    if (!q) continue

    const selectedOpt = q.options.find((o) => o.id === ans.selectedOption)
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
        k1_一元二次方程: '判别式运用不熟练，含参方程求解思路不清晰',
        k2_函数图像与性质: '二次函数对称性与顶点坐标计算掌握不足',
        k3_三角函数: '正弦定理灵活运用需要加强，周期判断有误',
        k4_数列: '通项公式与前 n 项和的关系理解不够深入',
        k5_概率与统计: '方差平移变换性质记忆混淆'
      }
      const suggestions: Record<string, string> = {
        k1_一元二次方程: '建议从判别式的几何意义出发，结合根的分布进行专项训练',
        k2_函数图像与性质: '建议通过描点法和函数图像变换进行操练',
        k3_三角函数: '建议结合单位圆理解正弦定理，系统整理三角恒等式',
        k4_数列: '建议从递推关系的角度理解 Sₙ 与 aₙ 的联系，多做转化练习',
        k5_概率与统计: '建议对比均值与方差的线性变换规则，建立清晰记忆模型'
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
  const errorCount = answers.value.filter((a) => {
    const q = questions.value.find((qq) => qq.id === a.questionId)
    const opt = q?.options.find((o) => o.id === a.selectedOption)
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
    (masteryLevels.reduce((s, m) => s + m.mastery, 0) / masteryLevels.length) * 100
  )

  const summaries: Record<string, string> = {
    excellent:
      '你的整体知识掌握非常扎实，认知负荷处于健康水平。建议保持当前的学习节奏，适当挑战更高难度的内容。',
    proficient:
      '你具备了良好的知识基础，部分知识点尚有提升空间。建议针对薄弱环节进行专项训练，进一步提升综合解题能力。',
    developing:
      '你的知识体系正在构建中，存在明显的薄弱环节。建议从基础概念出发，逐步加深理解，配合适量练习巩固知识点。',
    weak: '当前多个知识点掌握程度较低，认知负荷偏高。建议回归课本基础，先夯实核心概念，再逐步提升难度。'
  }

  let summaryKey: string
  if (overallScore >= 85) summaryKey = 'excellent'
  else if (overallScore >= 70) summaryKey = 'proficient'
  else if (overallScore >= 50) summaryKey = 'developing'
  else summaryKey = 'weak'

  return {
    id: `mock-${Date.now()}`,
    userId: '0',
    createdAt: new Date().toISOString(),
    subject: '人工智能导论',
    grade: '大学',
    masteryLevels,
    cognitiveLoad,
    learningStyle: overallScore >= 70 ? '视觉-逻辑型' : '循序渐进型',
    weakPoints,
    overallScore,
    summary: summaries[summaryKey] ?? ''
  }
}

/** 兜底诊断结果（当所有计算路径都失败时保证页面有内容渲染） */
function createFallbackResult(): DiagnosisResult {
  const now = new Date().toISOString()
  return {
    id: `fallback-${Date.now()}`,
    userId: '0',
    createdAt: now,
    subject: '人工智能导论',
    grade: '大学',
    masteryLevels: [
      { knowledgePoint: '基础知识', mastery: 0.65, level: 'developing', confidence: 0.7 }
    ],
    cognitiveLoad: {
      memoryLoad: 0.5,
      attentionLoad: 0.5,
      processingLoad: 0.5,
      overall: 0.5
    },
    learningStyle: '循序渐进型',
    weakPoints: [
      {
        knowledgePoint: '基础知识',
        reason: '系统暂时无法计算详细诊断，请稍后重试',
        severity: 'moderate',
        suggestedRemediation: '建议重新进行一次诊断评估'
      }
    ],
    overallScore: 65,
    summary:
      '系统诊断遇到问题，以上为粗略评估结果。建议稍后重新进行完整诊断以获得更精准的分析报告。'
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
      textStyle: { color: '#94A3B8', fontSize: 12 }
    },
    radar: {
      center: ['50%', '50%'],
      radius: '65%',
      indicator: sorted.map((item) => ({
        name: item.knowledgePoint,
        max: 1
      })),
      axisName: {
        color: '#94A3B8',
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
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
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
        axisTick: { distance: -18, length: 6, lineStyle: { width: 1, color: '#475569' } },
        splitLine: { distance: -22, length: 18, lineStyle: { width: 2, color: '#475569' } },
        axisLabel: {
          color: '#94A3B8',
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
          color: '#F8FAFC'
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
                <BulbOutlined style="color: #4a90d9" />
                <span
                  >每题作答后自动进入下一题，请认真思考后选择。系统将根据你的答题时间和正确率综合评估学习状态。</span
                >
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
          <span class="answered-text"> 已答 {{ answeredCount }} 题 </span>
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
        <a-card
          v-if="currentQuestion"
          :key="currentQuestion.id"
          class="question-card"
          :bordered="false"
        >
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
              <span
                v-else-if="showFeedback && selectedOption === opt.id && opt.weight !== 1"
                class="option-icon-wrong"
              >
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
        <a-button v-if="currentIndex > 0 && !showFeedback" @click="goPrevQuestion">
          上一题
        </a-button>
        <div class="footer-spacer" />
        <span v-if="isLastQuestion && answers.length >= totalQuestions" class="quiz-ready-text">
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
          {{ diagnosisResult.subject }} · {{ diagnosisResult.grade }} · 完成时间
          {{ new Date(diagnosisResult.createdAt).toLocaleString('zh-CN') }}
        </p>
        <div class="report-score-badge">
          <span class="score-number">{{ diagnosisResult.overallScore }}</span>
          <span class="score-label">综合评分</span>
        </div>
      </div>

      <!-- 图表行 -->
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
              <a-tag :color="loadLevelText(diagnosisResult.cognitiveLoad.overall).color">
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
              :stroke-color="
                diagnosisResult.cognitiveLoad.attentionLoad > 0.6 ? '#ff4d4f' : '#4A90D9'
              "
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
              :stroke-color="
                diagnosisResult.cognitiveLoad.processingLoad > 0.6 ? '#ff4d4f' : '#4A90D9'
              "
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
                  >
                    {{ levelText(item.level) }}
                  </a-tag>
                </div>
                <a-progress
                  :percent="Math.round(item.mastery * 100)"
                  :stroke-color="
                    item.mastery >= 0.7 ? '#52c41a' : item.mastery >= 0.4 ? '#faad14' : '#ff4d4f'
                  "
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

      <!-- AI 诊断摘要 -->
      <a-card class="summary-card" :bordered="false" title="AI 诊断摘要">
        <template #extra>
          <span class="learning-style-tag">{{ diagnosisResult.learningStyle }}</span>
        </template>
        <p class="summary-text">{{ diagnosisResult.summary }}</p>
      </a-card>

      <!-- 操作按钮 -->
      <div class="report-actions">
        <a-button type="primary" size="large" class="generate-path-btn" @click="goToGeneratePath">
          <RocketOutlined />
          生成学习路径
        </a-button>
        <a-button size="large" @click="restart">
          <ReloadOutlined />
          重新诊断
        </a-button>
        <a-button size="large" @click="router.push('/home')"> 返回首页 </a-button>
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
  background: linear-gradient(135deg, #e8d5b7 0%, #f5e6cc 100%);
  margin-bottom: 16px;
}

.start-icon {
  font-size: 36px;
  color: #4a6cf7;
}

.start-title {
  font-size: 26px;
  font-weight: 700;
  color: #f8fafc;
  margin: 0 0 8px;
}

.start-subtitle {
  font-size: 15px;
  color: #94a3b8;
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
  color: #4a6cf7;
  opacity: 0.8;
}

.info-label {
  font-size: 12px;
  color: #94a3b8;
}

.info-value {
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
}

.start-tips {
  margin: 12px 0;
}

.tips-content {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #d4a373;
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
  background: linear-gradient(135deg, #d4a373 0%, #c08b5c 100%);
  border: none;
  color: #0a0d14;
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
  color: #94a3b8;
}

.progress-text strong {
  color: #f8fafc;
  font-size: 16px;
}

.answered-text {
  font-size: 13px;
  color: #94a3b8;
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
  color: #f8fafc;
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
  border-color: rgba(74, 108, 247, 0.4);
  background: rgba(74, 108, 247, 0.08);
  transform: translateX(4px);
}

.option-selected {
  border-color: #d4a373;
  background: rgba(212, 163, 115, 0.12);
}

.option-correct {
  border-color: #34d399;
  background: rgba(52, 211, 153, 0.08);
  cursor: default;
}

.option-wrong {
  border-color: #f87171;
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
  color: #94a3b8;
  flex-shrink: 0;
  transition: all 0.25s;
}

.option-selected .option-label {
  background: #d4a373;
  color: #0a0d14;
}

.option-correct .option-label {
  background: #34d399;
  color: #0a0d14;
}

.option-wrong .option-label {
  background: #f87171;
  color: #fff;
}

.option-text {
  flex: 1;
  font-size: 15px;
  color: #e2e8f0;
  line-height: 1.5;
}

.option-icon-correct {
  color: #34d399;
  font-size: 20px;
}

.option-icon-wrong {
  color: #f87171;
  font-size: 20px;
}

/* 答题反馈 */
.question-feedback {
  margin-top: 20px;
}

/* 答题反馈 Alert 深色主题覆盖 */
.question-feedback :deep(.ant-alert) {
  border-radius: 10px;
  border: 1px solid;
  font-weight: 500;
  font-size: 15px;
}
.question-feedback :deep(.ant-alert-success) {
  background: rgba(52, 211, 153, 0.1);
  border-color: rgba(52, 211, 153, 0.3);
  color: #34d399;
}
.question-feedback :deep(.ant-alert-success .ant-alert-message) {
  color: #34d399;
}
.question-feedback :deep(.ant-alert-error) {
  background: rgba(248, 113, 113, 0.1);
  border-color: rgba(248, 113, 113, 0.3);
  color: #f87171;
}
.question-feedback :deep(.ant-alert-error .ant-alert-message) {
  color: #f87171;
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
  color: #94a3b8;
}

.dot-pulse {
  display: flex;
  gap: 6px;
}

.dot-pulse .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4a90d9;
  animation: dotPulse 1.4s infinite ease-in-out both;
}

.dot-pulse .dot:nth-child(1) {
  animation-delay: -0.32s;
}
.dot-pulse .dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes dotPulse {
  0%,
  80%,
  100% {
    transform: scale(0);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
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
  background: linear-gradient(135deg, #4a6cf7 0%, #1d4ed8 100%);
  color: #fff;
  font-size: 30px;
  margin-bottom: 12px;
}

.report-title {
  font-size: 26px;
  font-weight: 700;
  color: #f8fafc;
  margin: 0 0 6px;
}

.report-meta {
  font-size: 13px;
  color: #94a3b8;
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
  color: #d4a373;
  line-height: 1;
}

.score-label {
  font-size: 12px;
  color: #94a3b8;
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
  color: #94a3b8;
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
  color: #e2e8f0;
}

.mastery-confidence {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 4px;
  text-align: right;
}

/* 薄弱点 */
.weak-point-title {
  color: #f8fafc;
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
  color: #94a3b8;
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
  color: #e2e8f0;
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
  color: #94a3b8;
  line-height: 1.5;
  padding-left: 22px;
  position: relative;
}

.wp-reason-icon {
  font-size: 13px;
  color: #4a90d9;
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
  color: #e8d5b7;
  position: absolute;
  left: 12px;
  top: 10px;
}

/* AI 摘要 */
.summary-card {
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
  margin-bottom: 24px;
  border-left: 4px solid #4a90d9;
}

.summary-card :deep(.ant-card-head-title) {
  font-weight: 600;
  font-size: 15px;
}

.learning-style-tag {
  font-size: 12px;
  color: #4a90d9;
  font-weight: 500;
}

.summary-text {
  font-size: 14px;
  color: #94a3b8;
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
  background: linear-gradient(135deg, #4a90d9 0%, #3a7bc8 100%);
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
