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
        }

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const raw = line.slice(6).trim()
              if (raw === '[DONE]') continue
              try {
                const parsed = JSON.parse(raw)
                if (parsed.type === 'chunk' && parsed.content) {
                  full.answer += parsed.content
                  onChunk(parsed.content)
                } else if (parsed.type === 'done') {
                  Object.assign(full, parsed)
                  onDone(full)
                  return
                }
              } catch {
                // 非 JSON 行：当作纯文本增量
                if (raw) {
                  full.answer += raw
                  onChunk(raw)
                }
              }
            }
          }
        }

        onDone(full)
      } else {
        // 非流式响应：整体返回后用打字机效果
        const json: RAGQueryResponse = await response.json()
        onDone(json)
      }
    })
    .catch((err) => {
      if (err.name === 'AbortError') return
      onError(err instanceof Error ? err : new Error(String(err)))
    })
}
