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

  /** 获取备选路径方案（从 AOO 任务结果的 alternative_paths 提取） */
  getAlternatives(taskId: string): Promise<AlternativePath[]> {
    // 后端暂未独立提供该端点，通过状态接口降级获取
    return request
      .get<TaskStatusResponse>(`/aoo/status/${taskId}`)
      .then((resp) => (resp as unknown as TaskStatusResponse).alternativePaths ?? [])
  },

  /** 切换到备选路径方案 */
  selectPath(pathId: string): Promise<void> {
    return request.post<void>('/learning-paths/select', {
      path_id: pathId
    } as unknown as Record<string, unknown>)
  },

  /** 获取学习路径历史 */
  getHistory(): Promise<LearningPath[]> {
    return request.get<LearningPath[]>('/learning-paths/history')
  },

  /** 删除学习路径 */
  deletePath(pathId: string): Promise<void> {
    return request.delete<void>(`/learning-paths/${pathId}`)
  }
}
