import { request } from '@/api'

/** 反思判定请求（建议 9） */
export interface ReflectPayload {
  sessionId: string
  question: string
  material: string
  [key: string]: unknown
}

/** 反思判定响应（建议 9） */
export interface ReflectResult {
  understood: boolean
  feedback: string
  followUp: string
}

/** 会话画像提炼请求（建议 10） */
export interface SummarizeProfilePayload {
  sessionId: string
  userId: string
  authorized?: boolean
  [key: string]: unknown
}

/** 会话画像提炼响应（建议 10） */
export interface SummarizeProfileResult {
  deltas: { kpId: string; deltaMastery: number }[]
  newWeakPoints: string[]
  confidence: number
  significant: boolean
  replanned: boolean
  newVersion: number | null
}

export const chatApi = {
  /** 反思框：判定学生对可复制素材的理解度（建议 9） */
  reflect(payload: ReflectPayload): Promise<ReflectResult> {
    return request.post('/chat/reflect', payload)
  },
  /** 会话提炼画像：从对话提取掌握度增量并可能触发重规划（建议 10） */
  summarizeProfile(payload: SummarizeProfilePayload): Promise<SummarizeProfileResult> {
    return request.post('/chat/summarize-profile', payload)
  },
}
