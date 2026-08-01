import { request } from '@/api'
import type {
  DiagnosisQuestion,
  DiagnosisSubmitRequest,
  DiagnosisResult,
  DiagnosisBrief
} from '@/types'

/**
 * 认知诊断 API 模块
 */
export const diagnosisApi = {
  /** 获取诊断题目列表
   *  后端返回 QuestionsResponse { questions, total, subject, estimated_duration_min }
   *  经 axios 拦截器 unwrap 后此处返回的是 QuestionsResponse 对象
   *  调用方应读取 .questions 字段获取题目数组
   */
  getQuestions(subject?: string): Promise<{
    questions: DiagnosisQuestion[]
    total: number
    subject: string
    estimated_duration_min: number
  }> {
    return request.get('/diagnosis/questions', { subject }) as Promise<{
      questions: DiagnosisQuestion[]
      total: number
      subject: string
      estimated_duration_min: number
    }>
  },

  /** 提交诊断答案，返回诊断结果 */
  submit(data: DiagnosisSubmitRequest): Promise<DiagnosisResult> {
    return request.post<DiagnosisResult>(
      '/diagnosis/submit',
      data as unknown as Record<string, unknown>
    )
  },

  /** 获取最新诊断结果 */
  getLatest(): Promise<DiagnosisResult | null> {
    return request.get<DiagnosisResult | null>('/diagnosis/latest')
  },

  /** 根据 ID 获取诊断详情 */
  getById(id: string): Promise<DiagnosisResult> {
    return request.get<DiagnosisResult>(`/diagnosis/${id}`)
  },

  /** 获取诊断历史列表
   *  后端返回 DiagnosisHistoryResponse { items, total }
   *  本方法映射 items → list 保持前端一致性
   */
  async getHistory(params?: { page?: number; pageSize?: number }): Promise<{
    list: DiagnosisBrief[]
    total: number
  }> {
    const raw = await request.get<{ items: DiagnosisBrief[]; total: number }>(
      '/diagnosis/history',
      params as Record<string, unknown>
    )
    return { list: raw.items ?? [], total: raw.total ?? 0 }
  },

  /** 删除诊断记录 */
  delete(id: string): Promise<null> {
    return request.delete<null>(`/diagnosis/${id}`)
  },
}
