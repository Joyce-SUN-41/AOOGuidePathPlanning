import { request } from '@/api'
import type {
  CehuiQuestion,
  CehuiSubmitRequest,
  CehuiResult,
  CehuiBrief
} from '@/types'

/**
 * 学情测绘 API 模块
 */
export const cehuiApi = {
  /** 获取测绘题目列表
   *  后端返回 QuestionsResponse { questions, total, subject, estimated_duration_min }
   *  经 axios 拦截器 unwrap 后此处返回的是 QuestionsResponse 对象
   *  调用方应读取 .questions 字段获取题目数组
   */
  getQuestions(subject?: string): Promise<{
    questions: CehuiQuestion[]
    total: number
    subject: string
    estimated_duration_min: number
    allocation?: Record<string, Record<string, number>>
    graph_driven?: boolean
  }> {
    return request.get('/cehui/questions', { subject }) as Promise<{
      questions: CehuiQuestion[]
      total: number
      subject: string
      estimated_duration_min: number
      allocation?: Record<string, Record<string, number>>
      graph_driven?: boolean
    }>
  },

  /** 提交测绘答案，返回测绘结果 */
  submit(data: CehuiSubmitRequest): Promise<CehuiResult> {
    return request.post<CehuiResult>(
      '/cehui/submit',
      data as unknown as Record<string, unknown>
    )
  },

  /** 获取最新测绘结果 */
  getLatest(): Promise<CehuiResult | null> {
    return request.get<CehuiResult | null>('/cehui/latest')
  },

  /** 根据 ID 获取测绘详情 */
  getById(id: string): Promise<CehuiResult> {
    return request.get<CehuiResult>(`/cehui/${id}`)
  },

  /** 获取测绘历史列表
   *  后端返回 CehuiHistoryResponse { items, total }
   *  本方法映射 items → list 保持前端一致性
   */
  async getHistory(params?: { page?: number; pageSize?: number }): Promise<{
    list: CehuiBrief[]
    total: number
  }> {
    const raw = await request.get<{ items: CehuiBrief[]; total: number }>(
      '/cehui/history',
      params as Record<string, unknown>
    )
    return { list: raw.items ?? [], total: raw.total ?? 0 }
  },

  /** 删除测绘记录 */
  delete(id: string): Promise<null> {
    return request.delete<null>(`/cehui/${id}`)
  },
}
