import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ChatMessage, ChatExportData, SubjectOption } from '@/types/rag'

/** 对话最大保留轮次 */
const MAX_TURNS = 10

/** 预置学科选项（系统仅面向人工智能相关内容，选项均为 AI 方向细分领域） */
const SUBJECT_OPTIONS: SubjectOption[] = [
  { label: '人工智能导论', value: 'ai_intro', description: 'AI 基础概念、发展与应用全景' },
  { label: '机器学习', value: 'machine_learning', description: '经典机器学习算法与模型评估' },
  { label: '深度学习', value: 'deep_learning', description: '深度神经网络与训练优化' },
  { label: '自然语言处理', value: 'nlp', description: '文本理解、生成与大模型应用' },
  { label: '计算机视觉', value: 'cv', description: '图像识别、检测与视觉任务' },
  { label: '知识图谱与推理', value: 'kg_reasoning', description: '知识表示、图谱构建与 RAG 检索' },
]

function generateId(prefix = 'msg'): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

export const useChatStore = defineStore('chat', () => {
  // ── 状态 ──
  const messages = ref<ChatMessage[]>([])
  const isStreaming = ref(false)
  const isLoading = ref(false)
  const currentSubject = ref<string>('ai_intro')
  const currentSubjectLabel = ref<string>('人工智能导论')
  const lastQueryId = ref<string>('')
  const sessionId = ref<string>(generateId('sess'))
  const error = ref<string>('')
  const abortController = ref<AbortController | null>(null)

  // ── 计算属性 ──
  const messageCount = computed(() => messages.value.length)
  const lastMessage = computed(() => messages.value[messages.value.length - 1] || null)
  const subjects = computed(() => SUBJECT_OPTIONS)
  const canSend = computed(() => !isStreaming.value && !isLoading.value)

  /** 最近 10 轮用户-助手对话（不含系统消息），用于 API 上下文 */
  const recentTurns = computed<ChatMessage[]>(() => {
    const turns: ChatMessage[] = []
    let count = 0
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const msg = messages.value[i]
      if (!msg) continue
      if (msg.role !== 'system') {
        turns.unshift(msg)
        if (msg.role === 'user') count++
        if (count >= MAX_TURNS) break
      }
    }
    return turns
  })

  /** 获取 history 用于 API 调用 */
  const chatHistory = computed(() => {
    return recentTurns.value
      .filter((m) => m.role !== 'system')
      .map((m) => ({
        role: m.role,
        content: m.content,
      }))
  })

  // ── 动作 ──

  /** 切换学科 */
  function setSubject(value: string, label?: string) {
    currentSubject.value = value
    if (label) currentSubjectLabel.value = label
  }

  /** 添加用户消息 */
  function addUserMessage(content: string): ChatMessage {
    const msg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content,
      timestamp: Date.now(),
    }
    messages.value.push(msg)
    return msg
  }

  /** 添加空的助手消息（占位，用于流式追加） */
  function addAssistantPlaceholder(): ChatMessage {
    const msg: ChatMessage = {
      id: generateId(),
      role: 'assistant',
      content: '',
      isStreaming: true,
      timestamp: Date.now(),
    }
    messages.value.push(msg)
    return msg
  }

  /** 流式追加内容到当前助手消息 */
  function appendToAssistant(content: string) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant' && last.isStreaming) {
      last.content += content
    }
  }

  /** 完成助手消息 */
  function finishAssistant(data: {
    sources?: ChatMessage['sources']
    confidence?: number
    tokenUsage?: ChatMessage['tokenUsage']
    queryId?: string
  }) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.isStreaming = false
      if (data.sources) last.sources = data.sources
      if (data.confidence !== undefined) last.confidence = data.confidence
      if (data.tokenUsage) last.tokenUsage = data.tokenUsage
      if (data.queryId) last.queryId = data.queryId
    }
    isStreaming.value = false
    if (data.queryId) lastQueryId.value = data.queryId
  }

  /** 添加系统通知消息（非阻塞，追加到对话末尾） */
  function addSystemMessage(content: string) {
    messages.value.push({
      id: generateId(),
      role: 'system',
      content,
      timestamp: Date.now(),
    })
  }

  /** 添加系统的错误消息 */
  function addErrorMessage(errMsg: string) {
    // 移除最后一个空的 assistant placeholder
    if (
      messages.value.length > 0 &&
      messages.value[messages.value.length - 1]?.role === 'assistant' &&
      messages.value[messages.value.length - 1]?.isStreaming
    ) {
      messages.value.pop()
    }
    messages.value.push({
      id: generateId(),
      role: 'assistant',
      content: `抱歉，请求出错了：${errMsg}`,
      timestamp: Date.now(),
    })
  }

  /** 清空对话 */
  function clearChat() {
    messages.value = []
    error.value = ''
    lastQueryId.value = ''
    sessionId.value = generateId('sess')
    cancelStream()
  }

  /** 取消流式请求 */
  function cancelStream() {
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }
    isStreaming.value = false
    isLoading.value = false
  }

  /** 设置流式状态 */
  function startLoading() {
    isLoading.value = true
    isStreaming.value = true
    error.value = ''
    abortController.value = new AbortController()
  }

  function stopLoading() {
    isLoading.value = false
    isStreaming.value = false
    abortController.value = null
  }

  /** 设置错误 */
  function setError(err: string) {
    error.value = err
    isLoading.value = false
    isStreaming.value = false
  }

  /** 导出对话记录 */
  function exportChat(): ChatExportData {
    return {
      exportTime: new Date().toISOString(),
      subject: currentSubjectLabel.value,
      messages: messages.value
        .filter((m) => m.role !== 'system')
        .map((m) => ({
          role: m.role,
          content: m.content,
          sources: m.sources?.map((s) => ({
            document: s.document,
            page: s.page,
            content: s.content,
          })),
          timestamp: m.timestamp,
        })),
    }
  }

  /** 下载对话为 JSON 文件 */
  function downloadChat() {
    const data = exportChat()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `chat-${currentSubjectLabel.value}-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return {
    // 状态
    messages,
    isStreaming,
    isLoading,
    currentSubject,
    currentSubjectLabel,
    lastQueryId,
    sessionId,
    error,
    abortController,
    // 计算
    messageCount,
    lastMessage,
    subjects,
    canSend,
    recentTurns,
    chatHistory,
    // 方法
    setSubject,
    addUserMessage,
    addAssistantPlaceholder,
    appendToAssistant,
    finishAssistant,
    addSystemMessage,
    addErrorMessage,
    clearChat,
    cancelStream,
    startLoading,
    stopLoading,
    setError,
    exportChat,
    downloadChat,
  }
})
