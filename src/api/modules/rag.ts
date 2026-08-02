import { request, getToken } from '@/api'
import type {
  RAGQueryRequest,
  RAGQueryResponse,
  RAGStats,
  RAGIndexRequest,
  RAGIndexResponse,
} from '@/types/rag'

const BASE = '/rag'

export const ragApi = {
  /** RAG 问答
   *
   * 后端对单次 LLM 调用设了 90s 上限（LLM_CALL_TIMEOUT），
   * 前端超时必须留出余量（检索 + 序列化 + 网络），
   * 否则会在后端返回可读错误之前先抛出 "timeout of xxx ms exceeded"。
   */
  query(data: RAGQueryRequest): Promise<RAGQueryResponse> {
    return request.post<RAGQueryResponse>(
      `${BASE}/query`,
      { ...data, skip_retrieval: data.skip_retrieval ?? false } as unknown as Record<string, unknown>,
      { timeout: 150000 }
    )
  },

  /** 获取智能问答对话画像（仅来自对话梳理出的掌握特点）
   *
   * 后端端点: GET /api/v1/rag/chat-profile
   */
  getChatProfile(): Promise<ChatProfileData> {
    return request.get<ChatProfileData>(`${BASE}/chat-profile`)
  },

  /** 索引文档目录 */
  index(data: RAGIndexRequest): Promise<RAGIndexResponse> {
    return request.post<RAGIndexResponse>(
      `${BASE}/index`,
      data as unknown as Record<string, unknown>
    )
  },

  /** 获取知识库统计 */
  stats(): Promise<RAGStats> {
    return request.get<RAGStats>(`${BASE}/stats`)
  },

  /** 重置知识库 */
  reset(): Promise<{ message: string }> {
    return request.post<{ message: string }>(`${BASE}/reset`)
  },
}

/**
 * 流式 RAG 问答 (SSE)
 * 返回一个 ReadableStream reader，前端自行逐字消费
 */
export function ragQueryStream(
  data: RAGQueryRequest,
  onChunk: (text: string) => void,
  onDone: (full: RAGQueryResponse) => void,
  onError: (err: Error) => void,
  signal?: AbortSignal
): void {
  // 复用统一的 token 读取逻辑，避免与 axios 拦截器实现漂移
  const token = getToken() || ''

  // 与 request.download / tryRefreshToken 保持一致的 baseURL 兜底
  const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

  fetch(`${baseURL}${BASE}/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: token ? `Bearer ${token}` : '',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ ...data, stream: true }),
    signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.text().catch(() => '')
        throw new Error(err || `HTTP ${response.status}`)
      }

      const contentType = response.headers.get('content-type') || ''
      if (contentType.includes('text/event-stream')) {
        // SSE 流式解析
        const reader = response.body?.getReader()
        if (!reader) throw new Error('无法获取流式数据')
        const decoder = new TextDecoder()
        let buffer = ''

        const full: RAGQueryResponse = {
          answer: '',
          sources: [],
          confidence: 0,
          retrieval_count: 0,
          model: '',
          query_id: '',
          diagnosis: undefined,
        }
        // 后端以 {"error": "..."} 帧上报错误，暂存后在 [DONE] 时统一抛出
        let streamError = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue

            const raw = line.slice(6).trim()
            if (!raw) continue
            if (raw === '[DONE]') {
              if (streamError) onError(new Error(streamError))
              else onDone(full)
              return
            }

            try {
              const parsed = JSON.parse(raw)

              // 错误帧：记录下来，等 [DONE] 时统一上报
              if (parsed.error) {
                streamError = String(parsed.error)
                continue
              }
              // 来源帧
              if (Array.isArray(parsed.sources)) {
                full.sources = parsed.sources
                full.retrieval_count = parsed.sources.length
                continue
              }
              // 诊断帧
              if (parsed.diagnosis) {
                full.diagnosis = parsed.diagnosis
                continue
              }
              // query_id 帧
              if (parsed.query_id) {
                full.query_id = String(parsed.query_id)
                continue
              }
              // 增量内容帧
              const delta: string =
                typeof parsed.content === 'string' ? parsed.content : ''
              if (delta) {
                full.answer += delta
                onChunk(delta)
              }
            } catch {
              // 非 JSON 行：当作纯文本增量
              full.answer += raw
              onChunk(raw)
            }
          }
        }

        // 流结束但没收到 [DONE]（如连接中断）时的兜底
        if (streamError) onError(new Error(streamError))
        else onDone(full)
      } else {
        // 非流式回退：后端返回的是 ResponseBase 包裹结构，需要解包
        const json = await response.json()
        const body = (json?.data ?? json) as RAGQueryResponse
        if (json?.code && json.code !== 200 && json.code !== 0) {
          throw new Error(json.message || 'AI 服务暂时不可用')
        }
        onDone(body)
      }
    })
    .catch((err) => {
      if (err.name === 'AbortError') return
      onError(err instanceof Error ? err : new Error(String(err)))
    })
}

// ── 自动优化（对话诊断 → AOO 路径规划） ──
export interface AutoOptimizeParams {
  mastery_estimates: Array<{ kp_name: string; level: number }>
  cognitive_load: number
  learning_intent: string
  needs_optimization: boolean
  /** 重规划后是否自动采纳新版本（默认 false，仅生成待采纳版本供用户一键采纳） */
  auto_adopt?: boolean
}

export interface AutoOptimizeResult {
  triggered: boolean
  message: string
  aoo_task_id?: string
}

/** 对话诊断 → AOO 自动路径优化 */
export async function autoOptimize(
  params: AutoOptimizeParams
): Promise<AutoOptimizeResult> {
  const response = await request.post<AutoOptimizeResult>(
    `${BASE}/auto-optimize`,
    params as unknown as Record<string, unknown>,
    { timeout: 15000 }
  )
  return response
}

// ── 对话画像（仅来自智能问答梳理出的掌握特点） ──
export interface ChatProfileItem {
  kp_id: string
  kp_name: string
  /** 对话梳理出的掌握度 [0,1] */
  level: number
  /** 置信度 [0,1] */
  confidence: number
  /** 被对话修正的次数 */
  n: number
  /** 最近更新时间 ISO */
  last_at: string | null
  source: string
}

export interface ChatProfileData {
  exists: boolean
  chat_signal_count: number
  last_chat_at: string | null
  updated_at: string | null
  items: ChatProfileItem[]
}
