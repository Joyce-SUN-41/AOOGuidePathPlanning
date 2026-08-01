import { request } from '@/api'
import type {
  GeneratePathRequest,
  GeneratePathResponse,
  TaskStatusResponse,
  LearningPath,
  AlternativePath
} from '@/types'

/**
 * 学习路径 API 模块
 *
 * ⚠️ 后端实际端点位于 /aoo/*（AOO 优化引擎），不是 /path/*
 * 本模块统一封装路径规划相关的前端接口，内部重定向到正确的后端端点。
 */
export const pathApi = {
  /** 触发 AOO 异步生成学习路径
   *
   * 后端端点: POST /api/v1/aoo/optimize
   * 前端命名保持 pathApi.generate 以保持语义一致。
   */
  generate(data: GeneratePathRequest): Promise<GeneratePathResponse> {
    // 将前端偏好参数转换为后端 AOO 请求格式
    const { diagnosisId, preferences } = data
    const payload: Record<string, unknown> = {
      diagnosis_id: diagnosisId,
      // student_id 由后端从 token 提取，此处留空由拦截器或上层补齐
    }
    // 若上层传入 student_id，原样透传（教师端使用）
    if ((data as unknown as Record<string, unknown>)['studentId']) {
      payload['student_id'] = (data as unknown as Record<string, unknown>)['studentId']
    }
    // 偏好字段 → 后端 AOO config 超参 (近似映射)
    if (preferences?.intensity === 'intensive') {
      payload['config'] = { max_iterations: 800, population_size: 80 }
    } else if (preferences?.intensity === 'light') {
      payload['config'] = { max_iterations: 200, population_size: 30 }
    }
    if (preferences?.maxDays) {
      payload['preferences'] = { max_days: preferences.maxDays }
    }
    if (preferences?.focusAreas) {
      payload['focus_areas'] = preferences.focusAreas
    }
    return request.post<GeneratePathResponse>(
      '/aoo/optimize',
      payload
    )
  },

  /** 轮询 AOO 任务状态
   *
   * 后端端点: GET /api/v1/aoo/status/{task_id}
   */
  getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
    return request.get<TaskStatusResponse>(`/aoo/status/${taskId}`)
  },

  /** 获取指定路径详情 */
  getPath(pathId: string): Promise<LearningPath> {
    return request.get<LearningPath>(`/learning-paths/${pathId}`)
  },

  /** 获取用户当前活跃的学习路径 */
  getCurrentPath(): Promise<LearningPath | null> {
    return request.get<LearningPath | null>('/learning-paths/current')
  },

  /** 获取备选路径方案（速成冲刺 / 稳扎稳打 / 查漏补缺）
   *
   * 后端暂未独立提供该端点，通过状态接口降级获取。
   * 注意：备选方案位于 `result.alternativePaths`，不在响应顶层，
   * 早期实现读取顶层字段导致永远拿到空数组、标签页无法显示。
   */
  getAlternatives(taskId: string): Promise<AlternativePath[]> {
    return request.get<TaskStatusResponse>(`/aoo/status/${taskId}`).then((resp) => {
      const r = resp as unknown as Record<string, any>
      return (r?.['result']?.['alternativePaths'] ?? r?.['alternativePaths'] ?? []) as AlternativePath[]
    })
  },

  /** 获取寻优过程回放数据（收敛曲线 + 每代种群快照）
   *
   * 同样位于 `result.convergenceData`；状态响应顶层的 convergenceData
   * 只是「当前代」的单点快照，不含 iterations 数组，不能用于回放。
   */
  getConvergence(taskId: string): Promise<Record<string, unknown> | null> {
    return request.get<TaskStatusResponse>(`/aoo/status/${taskId}`).then((resp) => {
      const r = resp as unknown as Record<string, any>
      const conv = r?.['result']?.['convergenceData']
      return conv?.['iterations']?.length ? conv : null
    })
  },

  /** 切换到备选路径方案 */
  selectPath(pathId: string): Promise<void> {
    return request.post<void>('/learning-paths/select', {
      path_id: pathId
    } as unknown as Record<string, unknown>)
  },

  /** 获取学习路径历史（后端返回 { items, total }，此处拍平为数组） */
  getHistory(): Promise<LearningPath[]> {
    return request
      .get<{ items?: LearningPath[] } | LearningPath[]>('/learning-paths/history')
      .then((resp) => {
        if (Array.isArray(resp)) return resp
        return (resp as { items?: LearningPath[] })?.items ?? []
      })
  },

  /** 删除学习路径 */
  deletePath(pathId: string): Promise<void> {
    return request.delete<void>(`/learning-paths/${pathId}`)
  }
}
