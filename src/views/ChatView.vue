<script setup lang="ts">
/**
 * 智能问答页面 — AI 智能工作台
 *
 * 设计理念：让用户感觉在与智能生命体交流，而非填表格。
 * 视觉：动态粒子连线背景 + 噪点纹理 + 燕麦金/极光蓝 深色科技风。
 */
import { ref, computed, nextTick, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'
import { ragApi } from '@/api/modules/rag'
import type { QuickQuestion, RAGQueryResponse } from '@/types/rag'

// ── 子组件 ──
import ChatMessageComponent from '@/components/chat/ChatMessage.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import QuickQuestions from '@/components/chat/QuickQuestions.vue'

import {
  RobotOutlined,
  ClearOutlined,
  DownloadOutlined,
  DownOutlined,
  SendOutlined,
} from '@ant-design/icons-vue'

// ── Store ──
const chatStore = useChatStore()
const userStore = useUserStore()

// ── 本地状态 ──
const inputText = ref('')
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
    const p = particles[i]

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
      const a = particles[i]
      const b = particles[j]
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

// ── 打字机效果 ──
let typewriterTimer: number | null = null

function startTypewriter(fullText: string, onDone: () => void) {
  stopTypewriter()
  const CHARS_PER_FRAME = 3
  const FRAME_INTERVAL = 18
  let index = 0

  function tick() {
    if (index >= fullText.length) {
      stopTypewriter()
      onDone()
      return
    }
    const chunk = fullText.slice(index, index + CHARS_PER_FRAME)
    index += CHARS_PER_FRAME
    chatStore.appendToAssistant(chunk)
    scrollToBottom()
    typewriterTimer = window.setTimeout(tick, FRAME_INTERVAL)
  }
  tick()
}

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

// ── 发送消息 ──
async function handleSend() {
  const question = inputText.value.trim()
  if (!question || isStreaming.value) return

  inputText.value = ''

  chatStore.addUserMessage(question)
  chatStore.addAssistantPlaceholder()
  chatStore.startLoading()

  startThinkingAnimation()
  scrollToBottom()

  try {
    const response: RAGQueryResponse = await ragApi.query({
      question,
      top_k: 5,
      subject: chatStore.currentSubject,
      student_id: userStore.userInfo?.id ? String(userStore.userInfo.id) : undefined,
    })

    stopThinkingAnimation()

    const lastMsg = messages.value[messages.value.length - 1]
    if (lastMsg && lastMsg.role === 'assistant') {
      lastMsg.content = ''
    }

    if (!response.answer) {
      chatStore.finishAssistant({})
      chatStore.addErrorMessage('模型未返回有效回答')
      return
    }

    startTypewriter(response.answer, () => {
      chatStore.finishAssistant({
        sources: response.sources,
        confidence: response.confidence,
        tokenUsage: response.token_usage,
        queryId: response.query_id,
      })
      chatStore.stopLoading()
    })
  } catch (err: unknown) {
    stopThinkingAnimation()
    const msg = err instanceof Error ? err.message : '网络异常，请稍后重试'
    chatStore.addErrorMessage(msg)
    chatStore.stopLoading()
  }
}

function quickFill(text: string) {
  inputText.value = text
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
  ds_algo: [
    { id: 'q1', text: '什么是时间复杂度？', icon: 'question' },
    { id: 'q2', text: '解释快速排序的原理', icon: 'experiment' },
    { id: 'q3', text: 'BFS 和 DFS 的区别？', icon: 'bulb' },
    { id: 'q4', text: '什么是动态规划？', icon: 'thunderbolt' },
    { id: 'q5', text: '哈希表是如何解决冲突的？', icon: 'book' },
  ],
  os: [
    { id: 'q1', text: '进程和线程的区别？', icon: 'question' },
    { id: 'q2', text: '什么是死锁？如何避免？', icon: 'experiment' },
    { id: 'q3', text: '虚拟内存的工作原理', icon: 'bulb' },
    { id: 'q4', text: '解释 CPU 调度的几种算法', icon: 'thunderbolt' },
    { id: 'q5', text: '互斥锁与信号量的区别', icon: 'book' },
  ],
  network: [
    { id: 'q1', text: 'TCP 和 UDP 的区别？', icon: 'question' },
    { id: 'q2', text: 'OSI 七层模型是什么？', icon: 'experiment' },
    { id: 'q3', text: 'DNS 解析的过程是怎样的？', icon: 'bulb' },
    { id: 'q4', text: 'HTTP 和 HTTPS 的区别？', icon: 'thunderbolt' },
    { id: 'q5', text: '什么是三次握手和四次挥手？', icon: 'book' },
  ],
}

const currentQuickQuestions = ref<QuickQuestion[]>(quickQuestions)

function updateQuickQuestions(subject: string) {
  currentQuickQuestions.value = subjectQuestionsMap[subject] || quickQuestions
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
            <span class="toolbar-title">智能问答</span>
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
          <a-button type="text" size="small" :disabled="!hasMessages" @click="chatStore.clearChat()" title="清空对话">
            <template #icon><ClearOutlined /></template>
            清空
          </a-button>
          <a-button type="text" size="small" :disabled="!hasMessages" @click="chatStore.downloadChat()" title="导出对话">
            <template #icon><DownloadOutlined /></template>
            导出
          </a-button>
        </div>
      </div>

      <!-- 消息区域 -->
      <div ref="messagesContainer" class="messages-container" @scroll="handleScroll">
        <!-- 欢迎页面 -->
        <div v-if="showWelcome" class="welcome-area">
          <div class="welcome-glow" />
          <div class="welcome-icon">
            <RobotOutlined />
          </div>
          <h2 class="welcome-title">燕麦 · AI 智能工作台</h2>
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
</style>
