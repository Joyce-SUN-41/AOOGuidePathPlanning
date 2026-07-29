import { request } from '@/api'
import type {
  KnowledgePoint,
  KnowledgePointDetail,
  KnowledgeGraph,
  KnowledgePointForm,
  QuestionItem,
  QuestionForm,
  QuestionListResponse
} from '@/types'

/**
 * 知识点管理 API
 */
export const knowledgeApi = {
  /** 获取知识点列表 */
  list(params?: { subject?: string; layer?: string }): Promise<KnowledgePoint[]> {
    return request.get('/knowledge-points', params as Record<string, unknown>)
  },

  /** 获取知识图谱 (节点 + 边) */
  getGraph(): Promise<KnowledgeGraph> {
    return request.get('/knowledge-points/graph')
  },

  /** 获取知识点详情 */
  getById(id: string): Promise<KnowledgePointDetail> {
    return request.get(`/knowledge-points/${id}`)
  },

  /** 创建知识点 */
  create(data: KnowledgePointForm): Promise<KnowledgePoint> {
    return request.post('/knowledge-points', data as unknown as Record<string, unknown>)
  },

  /** 更新知识点 */
  update(id: string, data: Partial<KnowledgePointForm>): Promise<KnowledgePoint> {
    return request.put(`/knowledge-points/${id}`, data as unknown as Record<string, unknown>)
  },

  /** 删除知识点 */
  delete(id: string): Promise<void> {
    return request.delete(`/knowledge-points/${id}`)
  }
}

/**
 * 题库管理 API
 */
export const questionApi = {
  /** 获取题目列表 */
  list(params?: {
    subject?: string
    difficulty?: number
    kp_id?: string
    page?: number
    page_size?: number
  }): Promise<QuestionListResponse> {
    return request.get('/questions', params as Record<string, unknown>)
  },

  /** 获取题目详情 */
  getById(id: string): Promise<QuestionItem> {
    return request.get(`/questions/${id}`)
  },

  /** 创建题目 */
  create(data: QuestionForm): Promise<QuestionItem> {
    return request.post('/questions', data as unknown as Record<string, unknown>)
  },

  /** 更新题目 */
  update(id: string, data: Partial<QuestionForm>): Promise<QuestionItem> {
    return request.put(`/questions/${id}`, data as unknown as Record<string, unknown>)
  },

  /** 删除题目 */
  delete(id: string): Promise<void> {
    return request.delete(`/questions/${id}`)
  },

  /** 批量导入题目 */
  batchCreate(items: QuestionForm[]): Promise<{ created: number; skipped: number }> {
    return request.post('/questions/batch', items as unknown as Record<string, unknown>)
  }
}
