<script setup lang="ts">
/**
 * 导学终端页面 — AI 智能工作台
 *
 * 设计理念：让用户感觉在与智能生命体交流，而非填表格。
 * 视觉：动态粒子连线背景 + 噪点纹理 + 动麦金/极光蓝 深色科技风。
 */
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useIsMobile } from '@/composables/useIsMobile'
import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'
import { useCehuiStore } from '@/stores/cehui'
import { ragApi, ragQueryStream, autoOptimize } from '@/api/modules/rag'
import type { ChatProfileData } from '@/api/modules/rag'
import { chatApi } from '@/api/modules/chat'
import { trackEvent } from '@/utils/tracking'
import type { QuickQuestion, RAGQueryResponse } from '@/types/rag'

// ── 子组件 ──
import ChatMessageComponent from '@/components/chat/ChatMessage.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import QuickQuestions from '@/components/chat/QuickQuestions.vue'
import ReflectGate from '@/components/chat/ReflectGate.vue'

import {
  RobotOutlined,
  ClearOutlined,
  SwapOutlined,
  DownloadOutlined,
  DownOutlined,
  ProfileOutlined,
  QuestionOutlined,
} from '@ant-design/icons-vue'

// ── Store ──
const chatStore = useChatStore()
const userStore = useUserStore()
const cehuiStore = useCehuiStore()
const sessionId = chatStore.sessionId

// ── 移动端断点 ──
const { isMobile } = useIsMobile()

// ── 本地状态 ──
const inputText = ref('')
const firstChunkReceived = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)
const scrollBtnVisible = ref(false)
const thinkingDots = ref('')

// 快捷问题
const quickQuestions: QuickQuestion[] = [
  { id: 'q1', text: '什么是深度学习？', icon: 'question' },
  { id: 'q2', text: '解释反向传播算法的原理', icon: 'experiment' },
  { id: 'q3', text: 'CNN 和 RNN 有什么区别？', icon: 'bulb' },
  { id: 'q4', text: '什么是过拟合？如何防止？', icon: 'thunderbolt' },
  { id: 'q5', text: '介绍一下 Transformer 架构', icon: 'book' },
]

const messages = computed(() => chatStore.messages)
const isStreaming = computed(() => chatStore.isStreaming)
const isLoading = computed(() => chatStore.isLoading)
const hasMessages = computed(() => messages.value.length > 0)
const showWelcome = computed(() => !hasMessages.value && !isLoading.value)
const userName = computed(() => userStore.userInfo?.nickname || userStore.userInfo?.username || '我')

// ============================================================
//  粒子连线背景系统
// ============================================================
const canvasRef = ref<HTMLCanvasElement | null>(null)
let animationId: number | null = null
let mouseX = -1000
let mouseY = -1000

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  alpha: number
}

const PARTICLE_COUNT = 50
const CONNECTION_DIST = 180
const MOUSE_REPULSION_RADIUS = 120
let particles: Particle[] = []

function createParticles(w: number, h: number) {
  particles = []
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const angle = Math.random() * Math.PI * 2
    const speed = 0.2 + Math.random() * 0.3
    particles.push({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      radius: 1.5 + Math.random() * 1.5,
      alpha: 0.25 + Math.random() * 0.2,
    })
  }
}

function animate() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const W = canvas.width
  const H = canvas.height

  ctx.clearRect(0, 0, W, H)

  // 更新 & 绘制粒子
  for (let i = 0; i < particles.length; i++) {
    const p = particles[i]!

    // 移动
    p.x += p.vx
    p.y += p.vy

    // 边界反弹
    if (p.x < 0 || p.x > W) p.vx *= -1
    if (p.y < 0 || p.y > H) p.vy *= -1

    // 鼠标微弱斥力
    const dxM = p.x - mouseX
    const dyM = p.y - mouseY
    const distM = Math.sqrt(dxM * dxM + dyM * dyM)
    if (distM < MOUSE_REPULSION_RADIUS && distM > 0) {
      const force = (MOUSE_REPULSION_RADIUS - distM) / MOUSE_REPULSION_RADIUS
      p.x += (dxM / distM) * force * 0.8
      p.y += (dyM / distM) * force * 0.8
    }

    // 绘制粒子
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(212, 163, 115, ${p.alpha})`
    ctx.fill()
  }

  // 连线
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const a = particles[i]!
      const b = particles[j]!
      const dx = a.x - b.x
      const dy = a.y - b.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < CONNECTION_DIST) {
        const ratio = 1 - dist / CONNECTION_DIST
        const opacity = 0.05 + ratio * 0.25
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.strokeStyle = `rgba(212, 163, 115, ${opacity})`
        ctx.lineWidth = 0.6
        ctx.stroke()
      }
    }
  }

  animationId = requestAnimationFrame(animate)
}

function onMouseMove(e: MouseEvent) {
  mouseX = e.clientX
  mouseY = e.clientY
}

function resizeCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return
  const dpr = window.devicePixelRatio || 1
  canvas.width = window.innerWidth * dpr
  canvas.height = window.innerHeight * dpr
  canvas.style.width = window.innerWidth + 'px'
  canvas.style.height = window.innerHeight + 'px'
  const ctx = canvas.getContext('2d')
  if (ctx) ctx.scale(dpr, dpr)
}

// ── 打字机效果 (保留 stopTypewriter 以清理潜在定时器) ──
let typewriterTimer: number | null = null

function stopTypewriter() {
  if (typewriterTimer !== null) {
    clearTimeout(typewriterTimer)
    typewriterTimer = null
  }
}

// ── Thinking 动画 ──
let thinkingInterval: number | null = null

function startThinkingAnimation() {
  thinkingDots.value = ''
  let count = 0
  thinkingInterval = window.setInterval(() => {
    count = (count + 1) % 4
    thinkingDots.value = '.'.repeat(count)
  }, 400)
}

function stopThinkingAnimation() {
  if (thinkingInterval !== null) {
    clearInterval(thinkingInterval)
    thinkingInterval = null
  }
  thinkingDots.value = ''
}

// ── 重规划自动采纳开关（默认关，符合 P2 决策：默认生成待采纳版本供用户一键采纳）──
const autoAdoptEnabled = ref(false)

// ── 对话测绘 → AOO 自动优化触发 ──
// autoAdopt: 是否自动采纳重规划版本（默认 false，仅生成待采纳版本供用户一键采纳）
async function triggerAutoOptimize(
  cehui: NonNullable<RAGQueryResponse['cehui']>,
  autoAdopt = false
) {
  if (!cehui || !cehui.needs_optimization) return

  const masteryEstimates = cehui.mastery_estimates ?? []
  chatStore.addSystemMessage(
    `检测到 ${masteryEstimates.length > 0 ? masteryEstimates.filter(e => (e.level ?? 1) < 0.5).length : 0} ` +
    '个薄弱知识点，正在生成最优学习路径...'
  )

  try {
    const result = await autoOptimize({
      mastery_estimates: masteryEstimates.map((e: any) => ({
        kp_name: String(e.kp_name ?? ''),
        level: Number(e.level ?? 0.5),
      })),
      cognitive_load: cehui.cognitive_load ?? 0.5,
      learning_intent: String(cehui.learning_intent ?? 'quick_fix'),
      needs_optimization: true,
      auto_adopt: autoAdopt,
    })

    if (result.aoo_task_id) {
      if (autoAdopt) {
        chatStore.addSystemMessage(
          '已根据你的对话自动优化并采纳新的学习路径，可在路径看板查看。'
        )
      } else {
        chatStore.addSystemMessage(
          '已生成新版本学习路径（待采纳）。前往「我的路径」可查看变更详情并一键采纳。'
        )
      }
    } else {
      chatStore.addSystemMessage(result.message || '学习路径优化启动失败，请稍后重试。')
    }

    trackEvent('chat_aoo_auto_optimize', {
      triggered: result.triggered,
      task_id: result.aoo_task_id,
      auto_adopt: autoAdopt,
    })
  } catch (err: unknown) {
    chatStore.addSystemMessage(
      '路径优化服务暂时不可用，稍后可在测绘页面手动触发。'
    )
  }
}

// ── 发送消息（核心逻辑，支持带前缀的苏格拉底提示请求）──
const HINT_PREFIX = '[学生请求进一步提示，请给更细一级的引导，仍不直接给答案]'

async function sendMessage(text: string) {
  const question = text.trim()
  if (!question || isStreaming.value) return

  inputText.value = ''
  firstChunkReceived.value = false

  chatStore.addUserMessage(question)
  chatStore.addAssistantPlaceholder()
  chatStore.startLoading()

  startThinkingAnimation()
  scrollToBottom()

  // 埋点：不上报问题原文，仅记录长度与学科，避免敏感信息外泄
  const _queryStartedAt = Date.now()
  trackEvent('chat_query', {
    subject: chatStore.currentSubject ?? '',
    questionLength: question.length
  })

  // 累积完整回答用于 token 统计
  let fullAnswer = ''
  let _sources: RAGQueryResponse['sources'] = []
  let _queryId = ''

  try {
    await ragQueryStream(
      {
        question,
        top_k: 5,
        subject: chatStore.currentSubject,
        sessionId: chatStore.sessionId,
        student_id: userStore.userInfo?.id ? String(userStore.userInfo.id) : undefined,
        skip_retrieval: true,
        fast_mode: true,
        cehui_mode: true,
        stream: true,
      },
      // onChunk - 实时流式追加文本
      (chunk: string) => {
        if (!firstChunkReceived.value) {
          firstChunkReceived.value = true
          stopThinkingAnimation()
        }
        fullAnswer += chunk
        chatStore.appendToAssistant(chunk)
        scrollToBottom()
      },
      // onDone - 流式完成
      (full: RAGQueryResponse) => {
        _sources = full.sources ?? []
        _queryId = full.query_id

        stopThinkingAnimation()

        if (!fullAnswer && !full.answer) {
          chatStore.addErrorMessage('模型未返回有效回答')
          return
        }

        trackEvent('chat_response', {
          success: true,
          durationMs: Date.now() - _queryStartedAt,
          sourceCount: _sources.length,
          streaming: true,
        })

        const hasRetrieval = _sources.length > 0
        chatStore.finishAssistant({
          sources: _sources,
          confidence: hasRetrieval ? full.confidence : undefined,
          queryId: _queryId,
        })

        // 建议 9：助手消息含可复制素材（代码块/提纲）时，触发反思框锁定
        flagReusableMaterialForLastAssistant(fullAnswer)

        // 测绘模式：检测到薄弱知识点 → 自动触发 AOO 路径优化
        if (full.cehui?.needs_optimization) {
          triggerAutoOptimize(full.cehui, autoAdoptEnabled.value)
        }

        chatStore.stopLoading()
      },
      // onError
      (err: Error) => {
        stopThinkingAnimation()
        trackEvent('chat_response', {
          success: false,
          durationMs: Date.now() - _queryStartedAt
        })
        chatStore.addErrorMessage(err.message || '网络异常，请稍后重试')
        chatStore.stopLoading()
      },
    )
  } catch (err: unknown) {
    stopThinkingAnimation()
    const msg = err instanceof Error ? err.message : '网络异常，请稍后重试'
    trackEvent('chat_response', {
      success: false,
      durationMs: Date.now() - _queryStartedAt
    })
    chatStore.addErrorMessage(msg)
    chatStore.stopLoading()
  }
}

// ── 建议 9：反思框辅助 ──
// 判定助手消息是否含可复制使用素材。苏格拉底式引导回答以自然语言追问为主，
// 少有 ```代码块```，因此触发条件必须覆盖其常见「可复用素材」形态：
// 1) Markdown 代码块 / ~~~ 提纲块；
// 2) 显式标记 [可复用素材] / [可复制]（模型按提示词主动标注）；
// 3) 分步提纲：连续多行「1. / 2. 」或「步骤一 / 步骤二」等编号步骤；
// 4) 行内公式：$...$ 或 $$...$$（含 LaTeX 数学式）。
// 早期仅靠代码块导致反思框在苏格拉底模式下几乎永不出现（用户反馈“没实现”）。
// 分步提纲：需出现 2 个及以上连续编号项（避免单次列举就误触发反思框）
const REUSABLE_MATERIAL_RE =
  /```[\s\S]*?```|~~~[\s\S]*?~~~|(?:^|\n)(?:\s*(?:\d+[.、]|[一二三四五六七八九十]+[.、]|步骤[一二三四五六七八九十]+|Step\s*\d+)[)\s:：].*(?:\n|$)){2,}/
function hasReusableMaterial(content: string): boolean {
  if (!content) return false
  if (REUSABLE_MATERIAL_RE.test(content)) return true
  if (/\[可复用素材\]|\[可复制\]/.test(content)) return true
  // 行内/块级公式
  if (/\$[^$\n]+?\$|\$\$[\s\S]+?\$\$/.test(content)) return true
  return false
}

// 流式完成后：对最后一条助手消息做素材判定并置为锁定态
function flagReusableMaterialForLastAssistant(content: string) {
  const msgs = chatStore.messages
  if (!msgs.length) return
  const last = msgs[msgs.length - 1]
  if (!last || last.role !== 'assistant') return
  if (hasReusableMaterial(content)) {
    last.hasReusableMaterial = true
    if (last.reflectState !== 'unlocked') last.reflectState = 'locked'
    last.reflectResult = null
  }
}

const reflectingId = ref<string | null>(null)

// 提交反思：调用后端判定，更新锁定态
async function submitReflect(messageId: string, question: string) {
  const msg = chatStore.messages.find((m) => m.id === messageId)
  if (!msg) return
  msg.reflectState = 'reflecting'
  reflectingId.value = messageId
  try {
    const res = await chatApi.reflect({
      sessionId: sessionId,
      question,
      material: msg.content || '',
    })
    msg.reflectResult = {
      understood: res.understood,
      feedback: res.feedback,
      followUp: res.followUp,
    }
    msg.reflectState = res.understood ? 'unlocked' : 'locked'
  } catch {
    msg.reflectResult = {
      understood: false,
      feedback: '反思判定暂时不可用，请稍后再试。',
      followUp: '',
    }
    msg.reflectState = 'locked'
  } finally {
    reflectingId.value = null
  }
}

// 用新思路重生成：把学生思路拼成用户消息，复用现有流式链路
function requestRegenerate(newIdea: string) {
  const idea = `[学生新思路：${newIdea}] 请基于上述素材与我的新思路重新生成。`
  sendMessage(idea)
}

// ── 建议 10：计入学习画像开关 ──
const profileAuthorized = ref(false)
const summarizing = ref(false)

async function summarizeCurrentProfile() {
  if (!profileAuthorized.value || summarizing.value) return
  summarizing.value = true
  try {
    const res = await chatApi.summarizeProfile({
      sessionId: sessionId,
      userId: userStore.userInfo?.id ? String(userStore.userInfo.id) : '',
      authorized: true,
    })
    if (res.replanned) {
      chatStore.addSystemMessage(
        '已根据你的近期问答更新学习路径（待采纳）。前往「我的路径」可查看变更详情并一键采纳。',
      )
    } else if (res.deltas.length > 0) {
      chatStore.addSystemMessage('已将本次对话记入学习画像。')
    }
  } catch {
    // 静默失败，不影响对话
  } finally {
    summarizing.value = false
  }
}

// 普通发送：接收子组件上抛的当前文本，直接消费，避免依赖父级 inputText 的时序
function handleSend(text: string) {
  sendMessage(text)
}

// 建议 10：清空对话前，若授权则先提炼画像并可能触发重规划
async function handleClearChat() {
  if (profileAuthorized.value) {
    await summarizeCurrentProfile()
  }
  chatStore.clearChat()
}

// ── 苏格拉底式交互：请求更细一级提示（不改动流式协议，仅附加前缀）──
const showSocraticHint = computed(() => {
  if (isStreaming.value || !hasMessages.value) return false
  const msgs = messages.value
  const last = msgs[msgs.length - 1]
  if (!last || last.role !== 'assistant') return false
  const content = (last.content || '').trim()
  if (!content) return false
  // 助手以引导性问题结尾（中/英文问号），视为苏格拉底追问
  const lastChar = content.slice(-1)
  return lastChar === '?' || lastChar === '？'
})

async function requestSocraticHint() {
  if (isStreaming.value) return
  // 复用现有发送链路，自动附加苏格拉底提示前缀；保留用户输入（若有）作为补充
  const userExtra = inputText.value.trim()
  const prefixed = userExtra ? `${HINT_PREFIX}\n${userExtra}` : HINT_PREFIX
  await sendMessage(prefixed)
  inputText.value = ''
}

function quickFill(text: string) {
  inputText.value = text
}

// ── 对话画像抽屉 ──
// 仅展示「导学终端」通过对话梳理出的该生知识点掌握特点（与学情测绘严格分离）
const chatProfileVisible = ref(false)
const chatProfileLoading = ref(false)
const chatProfile = ref<ChatProfileData | null>(null)

async function openChatProfile() {
  chatProfileVisible.value = true
  chatProfileLoading.value = true
  try {
    const resp = await ragApi.getChatProfile()
    chatProfile.value = (resp as any)?.data ?? resp
  } catch (e) {
    console.error('[ChatView] 读取对话画像失败:', e)
    chatProfile.value = {
      exists: false,
      chat_signal_count: 0,
      last_chat_at: null,
      updated_at: null,
      items: [],
    }
  } finally {
    chatProfileLoading.value = false
  }
}

/** 掌握度 → 颜色（与测绘雷达图一致的动麦金/极光蓝语义） */
function profileLevelColor(level: number): string {
  if (level >= 0.75) return '#52c41a' // 掌握良好
  if (level >= 0.5) return '#4A6CF7' // 一般
  if (level >= 0.3) return '#D4A373' // 薄弱
  return '#ff4d4f' // 严重不足
}
function profileLevelText(level: number): string {
  if (level >= 0.75) return '良好'
  if (level >= 0.5) return '一般'
  if (level >= 0.3) return '薄弱'
  return '严重不足'
}
function formatProfileTime(iso?: string | null): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

// ── 自动滚动 ──
function scrollToBottom(smooth = true) {
  nextTick(() => {
    const el = messagesContainer.value
    if (el) {
      el.scrollTo({
        top: el.scrollHeight,
        behavior: smooth ? 'smooth' : 'auto',
      })
    }
  })
}

function handleScroll() {
  const el = messagesContainer.value
  if (!el) return
  const distToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  scrollBtnVisible.value = distToBottom > 200
}

// ── 学科切换 ──
function handleSubjectChange(value: string) {
  const subject = chatStore.subjects.find((s) => s.value === value)
  chatStore.setSubject(value, subject?.label)
  updateQuickQuestions(value)
}

const subjectQuestionsMap: Record<string, QuickQuestion[]> = {
  ai_intro: [
    { id: 'q1', text: '什么是图灵测试？', icon: 'question' },
    { id: 'q2', text: '解释 A* 搜索算法的原理', icon: 'experiment' },
    { id: 'q3', text: '什么是知识表示？有哪些方法？', icon: 'bulb' },
    { id: 'q4', text: '什么是监督学习与无监督学习？', icon: 'thunderbolt' },
    { id: 'q5', text: '介绍一下专家系统的基本结构', icon: 'book' },
  ],
  machine_learning: [
    { id: 'q1', text: '什么是过拟合？如何防止？', icon: 'question' },
    { id: 'q2', text: '解释 SVM 的核心思想', icon: 'experiment' },
    { id: 'q3', text: '决策树与随机森林的区别？', icon: 'bulb' },
    { id: 'q4', text: '什么是交叉验证？', icon: 'thunderbolt' },
    { id: 'q5', text: 'K-Means 聚类的原理是什么？', icon: 'book' },
  ],
  deep_learning: [
    { id: 'q1', text: '什么是深度学习？', icon: 'question' },
    { id: 'q2', text: '解释反向传播算法的原理', icon: 'experiment' },
    { id: 'q3', text: 'CNN 和 RNN 有什么区别？', icon: 'bulb' },
    { id: 'q4', text: '什么是 Transformer 架构？', icon: 'thunderbolt' },
    { id: 'q5', text: 'Batch Normalization 的作用？', icon: 'book' },
  ],
  nlp: [
    { id: 'q1', text: '什么是词嵌入？Word2Vec 的原理？', icon: 'question' },
    { id: 'q2', text: '解释注意力机制的核心思想', icon: 'experiment' },
    { id: 'q3', text: 'Transformer 与 RNN 处理序列有何不同？', icon: 'bulb' },
    { id: 'q4', text: '什么是大语言模型的微调与提示工程？', icon: 'thunderbolt' },
    { id: 'q5', text: '怎么评估机器翻译的质量？', icon: 'book' },
  ],
  cv: [
    { id: 'q1', text: 'CNN 的卷积层与池化层有什么作用？', icon: 'question' },
    { id: 'q2', text: '什么是目标检测？YOLO 的思路是什么？', icon: 'experiment' },
    { id: 'q3', text: '解释图像分割与分类的区别', icon: 'bulb' },
    { id: 'q4', text: '什么是数据增强？为什么有用？', icon: 'thunderbolt' },
    { id: 'q5', text: '迁移学习在计算机视觉中怎么用？', icon: 'book' },
  ],
  kg_reasoning: [
    { id: 'q1', text: '什么是知识图谱？它和关系数据库有何不同？', icon: 'question' },
    { id: 'q2', text: '什么是 RAG？它如何缓解大模型幻觉？', icon: 'experiment' },
    { id: 'q3', text: '解释实体、关系与属性的三元组表示', icon: 'bulb' },
    { id: 'q4', text: '向量检索是怎么工作的？', icon: 'thunderbolt' },
    { id: 'q5', text: '知识图谱怎么和大模型结合？', icon: 'book' },
  ],
}

const currentQuickQuestions = ref<QuickQuestion[]>(quickQuestions)

function updateQuickQuestions(subject: string) {
  currentQuickQuestions.value = subjectQuestionsMap[subject] || quickQuestions
}

// ── 条目12：测绘驱动导学终端 ──
// 从全局测绘 store 读取薄弱知识点与低准备度维度，生成可一键提问的引导话题
interface GuidedTopic {
  text: string
  reason: string
}

const diagGuidedTopics = computed<GuidedTopic[]>(() => {
  const diag = cehuiStore.currentCehui
  if (!diag) return []
  const topics: GuidedTopic[] = []
  // 薄弱知识点 → 请助手引导讲解（苏格拉底式）
  for (const wp of diag.weakPoints || []) {
    if (wp.knowledgePoint) {
      topics.push({
        text: `请引导我理解「${wp.knowledgePoint}」，不要直接给答案，先问我几个问题帮我理清思路`,
        reason: wp.reason || '该知识点掌握度偏低',
      })
    }
  }
  // 准备度偏低维度 → 提示调整方法
  const r = diag.readinessProfile
  if (r) {
    if ((r.selfEfficacy ?? 1) < 0.4) {
      topics.push({
        text: '我对自己学会这个知识点没什么信心，你有什么方法能帮我建立小步成功的体验？',
        reason: '自我效能偏低，建议从易到难拆分任务',
      })
    }
    if ((r.metacognition ?? 1) < 0.4) {
      topics.push({
        text: '我不太会规划自己的学习步骤，能教我怎么拆解一个知识点来复习吗？',
        reason: '元认知偏低，建议强化学习计划与自我监控',
      })
    }
  }
  // 认知负荷偏高 → 提示降低难度
  if ((diag.cognitiveLoad?.overall ?? 0) > 0.65) {
    topics.push({
      text: '刚才那部分内容我学起来很吃力，能换个更简单的方式再讲一遍吗？',
      reason: '本次测绘认知负荷偏高，建议降低讲解密度',
    })
  }
  return topics.slice(0, 4)
})

const showDiagGuided = computed(() => showWelcome.value && diagGuidedTopics.value.length > 0)

// ── 上浮知识粒子样式生成 ──
function sparkleStyle(n: number): Record<string, string> {
  const rng = (seed: number) => {
    const x = Math.sin(n * 99.7 + seed * 13.3) * 10000
    return x - Math.floor(x)
  }
  const left = (rng(1) * 100).toFixed(2)
  const size = (2 + rng(2) * 3).toFixed(1)
  const delay = (rng(3) * 14).toFixed(2)
  const duration = (12 + rng(4) * 12).toFixed(2)
  const hue = rng(5) > 0.5 ? '#D4A373' : '#4A6CF7'
  const opacity = (0.15 + rng(6) * 0.35).toFixed(2)
  return {
    left: left + '%',
    width: size + 'px',
    height: size + 'px',
    background: hue,
    opacity,
    animationDelay: '-' + delay + 's',
    animationDuration: duration + 's'
  }
}

// ── 生命周期 ──
onMounted(() => {
  updateQuickQuestions(chatStore.currentSubject)
  // 初始化粒子背景
  resizeCanvas()
  createParticles(window.innerWidth, window.innerHeight)
  animate()
  window.addEventListener('resize', handleResize)
  window.addEventListener('mousemove', onMouseMove)
})

function handleResize() {
  resizeCanvas()
  createParticles(window.innerWidth, window.innerHeight)
}

onBeforeUnmount(() => {
  stopTypewriter()
  stopThinkingAnimation()
  chatStore.cancelStream()
  if (animationId) cancelAnimationFrame(animationId)
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('mousemove', onMouseMove)
})
</script>

<template>
  <div class="chat-view">
    <!-- ========== 粒子连线背景 ========== -->
    <canvas ref="canvasRef" class="particle-canvas" />

    <!-- ========== 丰富化动态背景层 ========== -->
    <!-- 漂浮光斑层：缓慢游动的大光晕，营造呼吸感 -->
    <div class="bg-glow bg-glow--1" />
    <div class="bg-glow bg-glow--2" />
    <div class="bg-glow bg-glow--3" />
    <!-- 上浮知识粒子：缓慢上升的微光点 -->
    <div class="bg-sparkles">
      <span v-for="n in 18" :key="n" class="sparkle" :style="sparkleStyle(n)" />
    </div>
    <!-- 网格点阵：科技感基底 -->
    <div class="bg-grid" />

    <!-- ========== 噪点纹理叠加 ========== -->

    <!-- ========== 主内容区 ========== -->
    <div class="chat-shell">
      <!-- 顶部工具栏 -->
      <div class="chat-toolbar">
        <div class="toolbar-left">
          <div class="toolbar-brand">
            <div class="brand-icon">
              <RobotOutlined />
            </div>
            <span class="toolbar-title">导学终端</span>
          </div>
          <a-select
            :value="chatStore.currentSubject"
            :options="chatStore.subjects.map(s => ({ label: s.label, value: s.value }))"
            style="width: 180px"
            size="small"
            class="subject-select"
            @change="handleSubjectChange"
          >
            <template #option="{ label, value: optValue }">
              <div class="subject-option">
                <span class="so-label">{{ label }}</span>
                <span class="so-desc">{{ chatStore.subjects.find(s => s.value === optValue)?.description }}</span>
              </div>
            </template>
          </a-select>
        </div>
        <div class="toolbar-right">
          <a-button class="tb-btn" type="text" size="small" @click="openChatProfile()" title="查看由对话梳理出的掌握特点">
            <template #icon><ProfileOutlined /></template>
            <span class="tb-text">对话画像</span>
          </a-button>
          <a-tooltip title="授权后，本次对话将提炼为学习画像并可能更新你的路径">
            <span class="profile-auth">
              <a-switch
                v-model:checked="profileAuthorized"
                size="small"
                :disabled="summarizing"
              />
              <span class="tb-text profile-auth-text">计入学习画像</span>
            </span>
          </a-tooltip>
          <a-button class="tb-btn" type="text" size="small" :disabled="!hasMessages" @click="handleClearChat" title="清空对话">
            <template #icon><ClearOutlined /></template>
            <span class="tb-text">清空</span>
          </a-button>
          <a-button class="tb-btn" type="text" size="small" :disabled="!hasMessages" @click="chatStore.downloadChat()" title="导出对话">
            <template #icon><DownloadOutlined /></template>
            <span class="tb-text">导出</span>
          </a-button>
        </div>
      </div>

      <!-- 对话画像抽屉 -->
      <a-drawer
        v-model:open="chatProfileVisible"
        title="对话画像 · 导学终端梳理的掌握特点"
        placement="right"
        :width="isMobile ? '100%' : 420"
        :mask-closable="true"
      >
        <template #extra>
          <a-button size="small" :loading="chatProfileLoading" @click="openChatProfile()">刷新</a-button>
        </template>

        <a-spin :spinning="chatProfileLoading">
          <a-alert
            v-if="!chatProfile || !chatProfile.exists"
            class="chat-profile-empty"
            type="info"
            show-icon
            message="暂无对话画像"
            description="在对话中谈论具体知识点的掌握情况后，系统会自动梳理出你的掌握特点并在此展示。"
          />
          <template v-else>
            <div class="profile-meta">
              <span>基于 <b>{{ chatProfile.chat_signal_count }}</b> 次对话信号梳理</span>
              <span>最近更新：{{ formatProfileTime(chatProfile.last_chat_at) }}</span>
            </div>
            <a-divider style="margin: 12px 0" />
            <p class="profile-hint">
              以下内容<strong>仅来自导学终端对话</strong>，与「学情测绘」的客观答题结果相互独立，可用于「测绘 + 对话」重规划。
            </p>
            <a-list :data-source="chatProfile.items" size="small" :split="true">
              <template #renderItem="{ item }">
                <a-list-item>
                  <div class="profile-item">
                    <div class="pi-head">
                      <span class="pi-name">{{ item.kp_name }}</span>
                      <a-tag :color="profileLevelColor(item.level)">
                        {{ profileLevelText(item.level) }} · {{ Math.round(item.level * 100) }}%
                      </a-tag>
                    </div>
                    <a-progress
                      :percent="Math.round(item.level * 100)"
                      :stroke-color="profileLevelColor(item.level)"
                      :show-info="false"
                      size="small"
                    />
                    <div class="pi-foot">
                      <span>置信度 {{ Math.round(item.confidence * 100) }}%</span>
                      <span>对话修正 {{ item.n }} 次</span>
                      <span>{{ formatProfileTime(item.last_at) }}</span>
                    </div>
                  </div>
                </a-list-item>
              </template>
            </a-list>
          </template>
        </a-spin>
      </a-drawer>

      <!-- 消息区域 -->
      <div ref="messagesContainer" class="messages-container" @scroll="handleScroll">
        <!-- 欢迎页面 -->
        <div v-if="showWelcome" class="welcome-area">
          <div class="welcome-glow" />
          <div class="welcome-icon">
            <RobotOutlined />
          </div>
          <h2 class="welcome-title">动麦 · AI 智能工作台</h2>
          <p class="welcome-desc">
            基于 <strong>RAG 检索增强生成</strong> 技术，从学科教材、课件和论文中检索相关知识，
            由大模型生成专业、有据的解答。每一次对话都是一次深度探索。
          </p>
          <div class="welcome-features">
            <div class="wf-item">
              <span class="wf-dot" />
              <span>回答附带引用来源，可追溯原文</span>
            </div>
            <div class="wf-item">
              <span class="wf-dot" />
              <span>支持多轮对话，保持上下文连贯</span>
            </div>
            <div class="wf-item">
              <span class="wf-dot" />
              <span>快速切换学科知识库，精准检索</span>
            </div>
          </div>
          <div v-if="showDiagGuided" class="diag-guided">
            <div class="dg-head">
              <ProfileOutlined class="dg-icon" />
              <span>根据你的学情测绘，试试这些引导话题</span>
            </div>
            <div class="dg-list">
              <button
                v-for="(t, i) in diagGuidedTopics"
                :key="i"
                class="dg-item"
                @click="quickFill(t.text)"
              >
                <span class="dg-text">{{ t.text }}</span>
                <span class="dg-reason">{{ t.reason }}</span>
              </button>
            </div>
          </div>
        </div>

        <!-- 消息列表 -->
        <template v-for="msg in messages" :key="msg.id">
          <div
            v-if="msg.role === 'assistant' && msg.isStreaming && msg.content === ''"
            class="thinking-row"
          >
            <a-avatar :size="36" class="thinking-avatar">
              <template #icon><RobotOutlined /></template>
            </a-avatar>
            <div class="thinking-bubble">
              <span class="thinking-pulse" />
              <span class="thinking-label">正在检索知识库并生成回答</span>
              <span class="thinking-dots">{{ thinkingDots }}</span>
            </div>
          </div>
          <ChatMessageComponent
            v-else
            :message="msg"
            :user-name="userName"
          />
          <!-- 建议 9：助手消息含可复制素材时，展示反思框 -->
          <ReflectGate
            v-if="msg.role === 'assistant' && msg.hasReusableMaterial && msg.reflectState !== 'unlocked'"
            :reflecting="reflectingId === msg.id"
            :understood="msg.reflectResult?.understood"
            :feedback="msg.reflectResult?.feedback"
            :followUp="msg.reflectResult?.followUp"
            @submit-reflect="(q) => submitReflect(msg.id, q)"
            @request-regenerate="(idea) => requestRegenerate(idea)"
          />
        </template>

        <transition name="scroll-btn-fade">
          <div v-if="scrollBtnVisible" class="scroll-bottom-btn" @click="scrollToBottom()">
            <DownOutlined />
          </div>
        </transition>
      </div>

      <!-- 底部输入区域 -->
      <div class="chat-footer">
        <QuickQuestions
          v-if="showWelcome"
          :questions="currentQuickQuestions"
          @select="quickFill"
        />
        <!-- 苏格拉底式引导提示：助手以引导性问题结尾时，提示学生先自行回答 -->
        <transition name="socratic-fade">
          <div v-if="showSocraticHint" class="socratic-hint">
            <a-alert type="info" show-icon banner class="socratic-alert">
              <template #icon><QuestionOutlined /></template>
              <span class="socratic-text">助手留了一个引导性问题，试着先回答它，再继续对话</span>
            </a-alert>
            <a-button
              class="socratic-hint-btn"
              type="text"
              size="small"
              :disabled="isStreaming"
              @click="requestSocraticHint()"
            >
              <template #icon><QuestionOutlined /></template>
              我卡住了，再给一点提示
            </a-button>
          </div>
        </transition>
        <div class="chat-footer-options">
          <a-tooltip title="开启后，对话触发的路径优化将自动采纳新版本；默认关闭，仅生成待采纳版本供你一键确认">
            <span class="adopt-switch">
              <SwapOutlined />
              <span class="adopt-label">自动采纳新路径</span>
              <a-switch
                v-model:checked="autoAdoptEnabled"
                size="small"
                :disabled="!hasMessages"
              />
            </span>
          </a-tooltip>
        </div>
        <ChatInput
          v-model="inputText"
          :sending="isLoading"
          :has-content="hasMessages"
          @send="handleSend"
          @clear="chatStore.clearChat()"
          @export="chatStore.downloadChat()"
        />
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
/* ============================================================
   页面根容器 — 全屏底层
   ============================================================ */
.chat-view {
  position: relative;
  min-height: 100vh;
  background: #0A0D14;
  overflow: hidden;
}

/* ============================================================
   噪点纹理叠加层
   ============================================================ */
.chat-view::before {
  content: '';
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  pointer-events: none;
  z-index: 1;
  opacity: 0.035;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
  background-repeat: repeat;
  background-size: 256px 256px;
}

/* ============================================================
   粒子 Canvas 背景
   ============================================================ */
.particle-canvas {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 0;
  pointer-events: none;
}

/* ============================================================
   丰富化动态背景层（光斑 / 知识粒子 / 网格点阵）
   ============================================================ */
.bg-glow {
  position: fixed;
  border-radius: 50%;
  filter: blur(90px);
  pointer-events: none;
  z-index: 0;
  opacity: 0.5;
  mix-blend-mode: screen;
}
.bg-glow--1 {
  top: -12%;
  left: -8%;
  width: 46vw;
  height: 46vw;
  background: radial-gradient(circle at 50% 50%, rgba(212, 163, 115, 0.45), transparent 70%);
  animation: glowDrift1 26s ease-in-out infinite;
}
.bg-glow--2 {
  bottom: -18%;
  right: -10%;
  width: 52vw;
  height: 52vw;
  background: radial-gradient(circle at 50% 50%, rgba(74, 108, 247, 0.4), transparent 70%);
  animation: glowDrift2 32s ease-in-out infinite;
}
.bg-glow--3 {
  top: 30%;
  left: 45%;
  width: 38vw;
  height: 38vw;
  background: radial-gradient(circle at 50% 50%, rgba(0, 212, 255, 0.28), transparent 70%);
  animation: glowDrift3 38s ease-in-out infinite;
}
@keyframes glowDrift1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(8vw, 6vh) scale(1.12); }
}
@keyframes glowDrift2 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(-7vw, -5vh) scale(1.08); }
}
@keyframes glowDrift3 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(-5vw, 7vh) scale(1.15); }
}

.bg-sparkles {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}
.sparkle {
  position: absolute;
  bottom: -20px;
  border-radius: 50%;
  box-shadow: 0 0 6px 1px currentColor;
  animation-name: sparkleRise;
  animation-timing-function: linear;
  animation-iteration-count: infinite;
}
@keyframes sparkleRise {
  0% {
    transform: translateY(0) translateX(0);
    opacity: 0;
  }
  10% { opacity: 1; }
  90% { opacity: 0.8; }
  100% {
    transform: translateY(-105vh) translateX(20px);
    opacity: 0;
  }
}

.bg-grid {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(circle at 50% 40%, rgba(0, 0, 0, 0.6), transparent 75%);
  -webkit-mask-image: radial-gradient(circle at 50% 40%, rgba(0, 0, 0, 0.6), transparent 75%);
  opacity: 0.7;
}

/* ============================================================
   主内容外壳 — 浮于背景之上
   ============================================================ */
.chat-shell {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  height: calc((100vh - 56px) * 0.8);
  max-width: 960px;
  margin: 0 auto;
  padding: 0 16px;
  background: rgba(10, 13, 20, 0.70);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border-left: 1px solid rgba(255, 255, 255, 0.04);
  border-right: 1px solid rgba(255, 255, 255, 0.04);
}

/* ============================================================
   顶部工具栏
   ============================================================ */
.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
  flex-shrink: 0;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.toolbar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(74, 108, 247, 0.25), rgba(0, 212, 255, 0.10));
  border: 1px solid rgba(74, 108, 247, 0.25);
  font-size: 16px;
  color: #4A6CF7;
}

.toolbar-title {
  font-size: 16px;
  font-weight: 600;
  color: #F8FAFC;
}

.subject-select {
  :deep(.ant-select-selector) {
    background: rgba(255, 255, 255, 0.04) !important;
    border-color: rgba(255, 255, 255, 0.10) !important;
    color: #E2E8F0 !important;
  }
}

.subject-option {
  display: flex;
  flex-direction: column;
  gap: 1px;

  .so-label {
    font-size: 13px;
    color: #E2E8F0;
    font-weight: 500;
  }

  .so-desc {
    font-size: 11px;
    color: #64748B;
  }
}

.toolbar-right {
  display: flex;
  gap: 4px;

  :deep(.ant-btn-text) {
    color: #64748B;

    &:hover { color: #F8FAFC; }
    &:disabled { color: rgba(100, 116, 139, 0.3); }
  }
}

/* 桌面端：开关旁说明文字提升对比度，避免与外框颜色融合看不清 */
.profile-auth {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 4px;

  .profile-auth-text {
    color: #CBD5E1;
    font-size: 12px;
    user-select: none;
    white-space: nowrap;
  }
}

/* ============================================================
   移动端适配（≤768px）
   ============================================================ */
@media (max-width: 768px) {
  .chat-shell {
    /* 手机端顶部导航已占 56px，消息区铺满剩余高度，减少空旷感 */
    height: calc(100vh - 56px);
    padding: 0 12px 12px;
  }

  .chat-toolbar {
    flex-wrap: wrap;
    gap: 8px;
    padding: 10px 12px;
  }

  .toolbar-left {
    flex: 1;
    min-width: 0;
    gap: 8px;
  }

  .subject-select {
    /* 窄屏学科选择占满剩余宽度，避免 180px 固定值挤压 */
    width: 100% !important;
    max-width: 180px;
  }

  .toolbar-right {
    /* 按钮仅保留图标，文字隐藏，避免 toolbar 横向溢出 */
    flex-wrap: wrap;
    justify-content: flex-end;

    .tb-text {
      display: none;
    }

    :deep(.ant-btn-text) {
      padding: 0 8px;
    }
  }

  .profile-auth {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 0 6px;
  }
  .profile-auth-text {
    display: none;
  }

  .welcome-area {
    padding: 40px 16px 32px;
  }

  .welcome-title {
    font-size: 20px;
    letter-spacing: 0.5px;
  }

  .welcome-desc {
    font-size: 13px;
    max-width: 100%;
    margin-bottom: 24px;
  }
}

/* ============================================================
   消息容器
   ============================================================ */
.messages-container {
  flex: 1;
  overflow-y: auto;
  position: relative;
  scroll-behavior: smooth;

  &::-webkit-scrollbar {
    width: 5px;
  }

  &::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.08);
    border-radius: 10px;

    &:hover {
      background: rgba(255, 255, 255, 0.16);
    }
  }
}

/* ============================================================
   欢迎页 — AI 智能工作台氛围
   ============================================================ */
.welcome-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 40px 48px;
  text-align: center;
  position: relative;
}

.welcome-glow {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 320px;
  height: 320px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(74, 108, 247, 0.08), transparent 70%);
  pointer-events: none;
}

.welcome-icon {
  position: relative;
  width: 88px;
  height: 88px;
  border-radius: 22px;
  background: linear-gradient(135deg, rgba(74, 108, 247, 0.25), rgba(0, 212, 255, 0.12));
  border: 1px solid rgba(74, 108, 247, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 44px;
  color: #4A6CF7;
  margin-bottom: 28px;
  box-shadow:
    0 0 60px rgba(74, 108, 247, 0.12),
    inset 0 0 20px rgba(74, 108, 247, 0.08);
  animation: welcome-float 4s ease-in-out infinite;
}

@keyframes welcome-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

.welcome-title {
  font-size: 26px;
  font-weight: 700;
  color: #F8FAFC;
  margin: 0 0 14px;
  letter-spacing: 1px;
}

.welcome-desc {
  font-size: 14px;
  color: #64748B;
  line-height: 1.75;
  max-width: 480px;
  margin: 0 0 32px;

  strong {
    color: #D4A373;
    font-weight: 600;
  }
}

.welcome-features {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.wf-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: #94A3B8;
}

.wf-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #D4A373;
  flex-shrink: 0;
  box-shadow: 0 0 8px rgba(212, 163, 115, 0.5);
}

/* 测绘驱动引导话题 */
.diag-guided {
  margin-top: 28px;
  padding: 16px 18px;
  border-radius: 12px;
  background: rgba(212, 163, 115, 0.07);
  border: 1px solid rgba(212, 163, 115, 0.2);
  border-left: 3px solid #D4A373;
  text-align: left;
}

.dg-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #f0c894;
  margin-bottom: 12px;
}

.dg-icon {
  font-size: 15px;
}

.dg-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dg-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
  width: 100%;
  text-align: left;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #e2e8f0;
  cursor: pointer;
  transition: all 0.2s;
}

.dg-item:hover {
  border-color: rgba(212, 163, 115, 0.55);
  background: rgba(212, 163, 115, 0.1);
  transform: translateX(3px);
}

.dg-text {
  font-size: 13px;
  line-height: 1.5;
}

.dg-reason {
  font-size: 11px;
  color: #94a3b8;
}

/* ============================================================
   Thinking 动画 — 智能体"思考中"
   ============================================================ */
.thinking-row {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  align-items: center;
}

.thinking-avatar {
  background: linear-gradient(135deg, rgba(212, 163, 115, 0.35), rgba(184, 134, 11, 0.15));
  border: 1px solid rgba(212, 163, 115, 0.25);
  flex-shrink: 0;
}

.thinking-bubble {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: 14px;
  border-bottom-left-radius: 4px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.thinking-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #D4A373;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

.thinking-label {
  font-size: 13px;
  color: #94A3B8;
}

.thinking-dots {
  display: inline-block;
  width: 20px;
  text-align: left;
  color: #D4A373;
  font-weight: 600;
  letter-spacing: 1px;
}

/* ============================================================
   返回底部按钮
   ============================================================ */
.scroll-bottom-btn {
  position: absolute;
  bottom: 16px;
  right: 20px;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: rgba(10, 13, 20, 0.85);
  border: 1px solid rgba(212, 163, 115, 0.2);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #D4A373;
  transition: all 0.25s;
  z-index: 10;

  &:hover {
    border-color: rgba(212, 163, 115, 0.5);
    box-shadow: 0 4px 20px rgba(212, 163, 115, 0.2);
    transform: translateY(-2px);
  }
}

.scroll-btn-fade-enter-active,
.scroll-btn-fade-leave-active {
  transition: opacity 0.25s, transform 0.25s;
}

.scroll-btn-fade-enter-from,
.scroll-btn-fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

/* ============================================================
   底部输入区域
   ============================================================ */
.chat-footer {
  flex-shrink: 0;
  background: rgba(10, 13, 20, 0.80);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.chat-footer-options {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 8px 20px 0;

  .adopt-switch {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: #CBD5E1;
    cursor: default;

    .adopt-label {
      user-select: none;
      white-space: nowrap;
    }
  }
}

/* ============================================================
   苏格拉底式引导提示区 — 助手以引导性问题结尾时出现的引导条
   ============================================================ */
.socratic-hint {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 20px 0;
}

.socratic-alert.ant-alert {
  flex: 1;
  background: rgba(212, 163, 115, 0.08);
  border: 1px solid rgba(212, 163, 115, 0.30);
  border-radius: 6px;

  :deep(.ant-alert-icon) {
    color: #D4A373;
  }
  :deep(.ant-alert-message) {
    color: #E2E8F0;
  }
}

.socratic-text {
  font-size: 12.5px;
  color: #CBD5E1;
  line-height: 1.5;
}

.socratic-hint-btn {
  flex-shrink: 0;
  color: #D4A373 !important;
  border: 1px solid rgba(212, 163, 115, 0.30) !important;
  border-radius: 6px;
  font-size: 12px;

  &:hover:not(:disabled) {
    color: #F8FAFC !important;
    border-color: rgba(212, 163, 115, 0.6) !important;
    background: rgba(212, 163, 115, 0.10) !important;
  }
  &:disabled {
    color: rgba(212, 163, 115, 0.4) !important;
  }
}

.socratic-fade-enter-active,
.socratic-fade-leave-active {
  transition: opacity 0.25s, transform 0.25s;
}
.socratic-fade-enter-from,
.socratic-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* 移动端：苏格拉底提示区纵向堆叠，按钮占满宽度 */
@media (max-width: 768px) {
  .socratic-hint {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  .socratic-hint-btn {
    width: 100%;
  }
}

/* ============================================================
   对话画像抽屉
   ============================================================ */
.profile-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #94A3B8;
  margin-bottom: 4px;

  b {
    color: #D4A373;
  }
}
.profile-hint {
  font-size: 12px;
  color: #64748B;
  line-height: 1.6;
  margin: 0 0 12px;
  padding: 8px 10px;
  background: rgba(74, 108, 247, 0.08);
  border-left: 2px solid #4A6CF7;
  border-radius: 4px;

  strong {
    color: #4A6CF7;
  }
}
/* 对话画像空态提示：深色主题适配，避免默认浅蓝底与边框糊在一起 */
.chat-profile-empty.ant-alert {
  background: rgba(74, 108, 247, 0.10);
  border: 1px solid rgba(74, 108, 247, 0.45);
  border-radius: 8px;
  padding: 12px 14px;

  .ant-alert-icon {
    color: #4A6CF7;
  }
  .ant-alert-message {
    color: #E2E8F0;
    font-weight: 600;
  }
  .ant-alert-description {
    color: #94A3B8;
    line-height: 1.6;
  }
}
.profile-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pi-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.pi-name {
  font-size: 13px;
  font-weight: 600;
  color: #F8FAFC;
}
.pi-foot {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #64748B;
  flex-wrap: wrap;
}
</style>
