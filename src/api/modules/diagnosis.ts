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
  /** 获取诊断题目列表 */
  getQuestions(subject?: string): Promise<DiagnosisQuestion[]> {
    return request.get<DiagnosisQuestion[]>('/diagnosis/questions', { subject })
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

  /** 获取诊断历史列表 */
  getHistory(params?: { page?: number; pageSize?: number }): Promise<{
    list: DiagnosisBrief[]
    total: number
  }> {
    return request.get('/diagnosis/history', params as Record<string, unknown>)
  }
}
