// ============= RAG 知识库 / 智能问答类型 =============

/** RAG 检索来源 */
export interface RAGSource {
  document: string
  page?: number
  section?: string
  content: string
  score: number // 相似度 0-1
  ref: number // 引用编号
}

/** RAG Token 用量 */
export interface RAGTokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

/** RAG 查询请求 */
export interface RAGQueryRequest {
  question: string
  top_k?: number
  temperature?: number
  max_tokens?: number
  student_id?: string
  subject?: string
  /** true = 跳过知识库检索直连大模型；默认 false（走 RAG 检索增强） */
  skip_retrieval?: boolean
  /** true = 快速模式（低温度、短回复、短超时） */
  fast_mode?: boolean
  /** true = 诊断模式（附加学习状态评估 JSON） */
  diagnose_mode?: boolean
  /** true = 走 SSE 流式返回（仅 ragQueryStream 使用） */
  stream?: boolean
}

/** RAG 查询响应 */
export interface RAGQueryResponse {
  answer: string
  sources: RAGSource[]
  confidence: number
  retrieval_count: number
  model: string
  token_usage?: RAGTokenUsage
  query_id: string
  /** 诊断模式下的学习评估数据 */
  diagnosis?: {
    mastery_estimates?: Array<{ kp_name: string; level: number }>
    cognitive_load?: number
    learning_intent?: string
    needs_optimization?: boolean
  }
}

/** RAG 知识库统计 */
export interface RAGStats {
  collection_name: string
  total_documents: number
  total_chunks: number
  indexed_files: string[]
}

/** RAG 索引请求 */
export interface RAGIndexRequest {
  directory: string
  recursive?: boolean
}

/** RAG 索引响应 */
export interface RAGIndexResponse {
  total_chunks: number
  indexed_files: string[]
  errors: string[]
}

// ============= 对话前端类型 =============

/** 对话角色 */
export type ChatRole = 'user' | 'assistant' | 'system'

/** 学科选项 */
export interface SubjectOption {
  label: string
  value: string
  description?: string
}

/** 单条对话消息 */
export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  sources?: RAGSource[]
  confidence?: number
  tokenUsage?: RAGTokenUsage
  timestamp: number
  isStreaming?: boolean // 是否正在流式输出
  queryId?: string
}

/** 快捷提问项 */
export interface QuickQuestion {
  id: string
  text: string
  icon?: string
}

/** 对话导出格式 */
export interface ChatExportData {
  exportTime: string
  subject: string
  messages: {
    role: ChatRole
    content: string
    sources?: {
      document: string
      page?: number
      content: string
    }[]
    timestamp: number
  }[]
}
