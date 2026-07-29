import { request } from '@/api'
import type {
  ClassOverview,
  StudentSummary,
  WeakKpStat,
  MasteryTrendPoint,
  AlertStudent,
  StudentDetail,
  TeacherDashboardData
} from '@/types'

/**
 * 教师仪表盘 API 模块
 *
 * 注意：后端 ResponseBase 的 data 字段已被 axios 响应拦截器自动提取（code=200 时）。
 * 但部分端点（如 /students）的 data 内部仍包裹在 {students, total} 对象中，
 * 此处统一在 API 层完成二次解包。
 */

/** 通用解包：若 data 为 {students, total} 则提取 students */
function _unwrapArray<T>(data: unknown, key: string = 'students'): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object' && key in (data as Record<string, unknown>)) {
    return ((data as Record<string, unknown>)[key] as T[]) ?? []
  }
  return []
}

export const teacherApi = {
  /** 获取班级概览统计数据 */
  getClassOverview(): Promise<ClassOverview> {
    return request.get<ClassOverview>('/teacher/class-overview')
  },

  /** 获取学生列表（含学情摘要） */
  async getStudents(params?: {
    page?: number
    pageSize?: number
    sortBy?: string
    order?: 'asc' | 'desc'
  }): Promise<StudentSummary[]> {
    const data = await request.get<unknown>('/teacher/students', params as Record<string, unknown>)
    return _unwrapArray<StudentSummary>(data, 'students')
  },

  /** 获取全班共性薄弱知识点 Top N */
  async getWeakKps(topN?: number): Promise<WeakKpStat[]> {
    const data = await request.get<unknown>('/teacher/weak-knowledge-points', { top_n: topN ?? 5 })
    return _unwrapArray<WeakKpStat>(data, 'data')
  },

  /** 获取全班掌握度变化趋势 */
  async getMasteryTrend(days?: number): Promise<MasteryTrendPoint[]> {
    const data = await request.get<unknown>('/teacher/mastery-trend', { days: days ?? 30 })
    return _unwrapArray<MasteryTrendPoint>(data, 'data')
  },

  /** 获取预警学生列表 */
  async getAlerts(): Promise<AlertStudent[]> {
    const data = await request.get<unknown>('/teacher/alerts')
    return _unwrapArray<AlertStudent>(data, 'data')
  },

  /** 获取单个学生学情详情 */
  getStudentDetail(studentId: number): Promise<StudentDetail> {
    return request.get<StudentDetail>(`/teacher/students/${studentId}`)
  },

  /** 获取教师仪表盘聚合数据（一次性获取所有数据，减少请求） */
  getDashboardData(): Promise<TeacherDashboardData> {
    return request.get<TeacherDashboardData>('/teacher/dashboard')
  }
}
