import { request } from '@/api'
import type {
  CognitiveLoadTrendPoint,
  DailyActivityItem,
  LearningSuggestion,
  DashboardOverview
} from '@/types'

/**
 * 学情看板 API 模块
 *
 * Dashboard 数据跨诊断结果 + 学习路径 + 学习行为聚合，
 * 后端若尚未实现对应端点，调用方应 catch 异常后使用 fallback。
 */
export const dashboardApi = {
  /** 获取认知负荷历史趋势（最近 N 次诊断） */
  getCognitiveLoadTrend(limit = 10): Promise<CognitiveLoadTrendPoint[]> {
    return request.get<CognitiveLoadTrendPoint[]>('/dashboard/cognitive-load-trend', { limit })
  },

  /** 获取某月的每日学习活动（热力图） */
  getCalendarActivity(year: number, month: number): Promise<DailyActivityItem[]> {
    return request.get<DailyActivityItem[]>('/dashboard/calendar-activity', { year, month })
  },

  /** 获取 AI 学习建议（基于星火大模型分析） */
  getSuggestions(): Promise<LearningSuggestion[]> {
    return request.get<LearningSuggestion[]>('/dashboard/suggestions')
  },

  /** 获取看板概览数据 */
  getOverview(): Promise<DashboardOverview> {
    return request.get<DashboardOverview>('/dashboard/overview')
  }
}
