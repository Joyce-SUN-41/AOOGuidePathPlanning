// ============= AOO 可视化数据接口契约 =============
// 与后端 app/schemas/aoo.py 严格同步，JSON key 统一使用小驼峰（camelCase）

// ============================================================
// 核心：收敛曲线数据
// ============================================================

/** 种群快照 — 单个迭代的个体分布（散点图/动画用） */
export interface PopulationSnapshot {
  /** 个体适应度值列表 */
  fitnessValues: number[]
  /** 个体在解空间中的 x 坐标（降维后） */
  positionsX: number[]
  /** 个体在解空间中的 y 坐标（降维后） */
  positionsY: number[]
  /** 颜色标签：'elite' | 'normal' | 'exploring' */
  colors: string[]
  /** 该迭代的最佳个体索引 */
  bestIndex: number
}

/** AOO 收敛曲线全部数据 */
export interface AOOConvergenceData {
  /** 迭代轮次序列 [1, 2, 3, ...] */
  iterations: number[]

  /** 每代最佳适应度序列，单调非递减 */
  bestFitness: number[]

  /** 每代平均适应度序列 */
  avgFitness: number[]

  /** 每代种群多样性序列 [0, 1] */
  diversity: number[]

  /** 每代中位数适应度（用于箱线图或分布带） */
  medianFitness: number[]

  /** 每代 Q1 / Q3 四分位距（用于误差带可视化） */
  q1Fitness: number[]
  q3Fitness: number[]

  /** 种群快照列表 — 用于散点图动画，前端按迭代索引播放 */
  populationSnapshots?: PopulationSnapshot[]

  /** 元信息 */
  metadata: ConvergenceMetadata
}

/** 收敛过程元信息 */
export interface ConvergenceMetadata {
  /** 算法名称 */
  algorithm: string // 'AOO'
  /** 种群规模 */
  populationSize: number
  /** 精英保留数 */
  eliteCount: number
  /** 最终收敛率 (last best / theoretical optimum × 100) */
  convergenceRate: number
  /** 收敛所需迭代数（达到 95% 最优解的代数） */
  convergenceIteration: number
  /** 总优化耗时（秒） */
  totalTimeSeconds: number
}

// ============================================================
// 核心：学习路径结构（收敛数据嵌入返回体）
// ============================================================

/** 路径中的单个学习任务 */
export interface PathTaskInDay {
  /** 任务名称 */
  name: string
  /** 预估耗时（分钟） */
  duration: number
  /** 任务类型 */
  type: 'video' | 'quiz' | 'reading' | 'project' | 'exercise'
  /** 关联知识点 */
  knowledgePoint?: string
  /** 难度等级 1-5 */
  difficulty?: number
}

/** 路径中的一天 */
export interface PathDay {
  /** 第几天（从 1 开始） */
  day: number
  /** 当天任务列表 */
  tasks: PathTaskInDay[]
  /** 当天总预估耗时（分钟） */
  totalMinutes: number
  /** 当天平均难度 */
  avgDifficulty: number
}

/** 最优路径摘要 */
export interface BestPath {
  /** 按天组织的学习路径 */
  days: PathDay[]
  /** 适应度得分 [0, 1] */
  totalFitness: number
  /** 总天数 */
  totalDays: number
  /** 总任务数 */
  totalTasks: number
  /** 总预估小时数 */
  totalEstimatedHours: number
}

/** AOO 生成结果（嵌入 TaskStatusResponse.result） */
export interface AOOLearningPathResult {
  /** 最优路径 */
  bestPath: BestPath
  /** 收敛数据 — 前端直接绑定图表 */
  convergence: AOOConvergenceData
}

// ============================================================
// 对外暴露：完整 API 响应体
// ============================================================

/** GET /api/v1/path/task/{taskId} — 任务状态轮询响应 */
export interface AOOLearningPathResponse {
  taskId: string
  status: AOOOptimizationStatus
  /** 进度百分比 [0, 100] */
  progress: number
  /** 完成后返回路径 + 收敛数据 */
  result?: AOOLearningPathResult
  /** 失败时的错误信息 */
  errorMessage?: string
  /** 预估剩余秒数 */
  estimatedRemainingSeconds?: number
}

/** AOO 优化任务状态 */
export type AOOOptimizationStatus =
  | 'pending'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'

// ============================================================
// 图表绑定辅助类型
// ============================================================

/** 收敛曲线图 X/Y 数据点 */
export interface ChartPoint {
  x: number
  y: number
}

/** ECharts 收敛曲线 series 配置项（前端直接使用） */
export interface ConvergenceSeriesConfig {
  name: string
  type: 'line'
  data: [number, number][] // [[iteration, value], ...]
  smooth: boolean
  lineStyle: { color: string; width: number }
  areaStyle?: { color: string; opacity: number }
}

/** 种群散点图数据帧（动画用） */
export interface PopulationFrame {
  currentIteration: number
  data: [number, number][] // [[x, y], ...] 降维后的个体坐标
  bestPoint: [number, number]
  diversity: number
}

// ============================================================
// 请求体类型
// ============================================================

/** POST /api/v1/path/generate — 触发 AOO 路径生成 */
export interface AOOGenerateRequest {
  diagnosisId: string
  /** 可选的偏好配置 */
  preferences?: AOOPreferences
}

/** AOO 优化偏好参数 */
export interface AOOPreferences {
  /** 最大学习天数限制 */
  maxDays?: number
  /** 重点关注的薄弱知识点 */
  focusAreas?: string[]
  /** 学习强度 */
  intensity?: 'light' | 'moderate' | 'intensive'
  /** 每日最大学习时长（分钟） */
  maxDailyMinutes?: number
  /** 种群规模（默认 50） */
  populationSize?: number
  /** 最大迭代次数（默认 200） */
  maxIterations?: number
}

// ============================================================
// 类型守卫 & 工具函数
// ============================================================

/** 检查响应是否已完成 */
export function isOptimizationCompleted(
  response: AOOLearningPathResponse
): response is AOOLearningPathResponse & {
  result: AOOLearningPathResult
} {
  return response.status === 'completed' && response.result !== undefined
}

/** 检查响应是否失败 */
export function isOptimizationFailed(
  response: AOOLearningPathResponse
): boolean {
  return response.status === 'failed'
}

/** 检查响应是否在运行中 */
export function isOptimizationRunning(
  response: AOOLearningPathResponse
): boolean {
  return ['pending', 'queued', 'processing'].includes(response.status)
}

/** 从收敛数据构造 ECharts 收敛曲线 series */
export function buildConvergenceSeries(
  data: AOOConvergenceData
): ConvergenceSeriesConfig[] {
  return [
    {
      name: '最佳适应度',
      type: 'line',
      data: data.iterations.map((it, i) => [it, data.bestFitness[i]]),
      smooth: true,
      lineStyle: { color: '#4F7CFF', width: 2.5 },
      areaStyle: { color: '#4F7CFF', opacity: 0.08 },
    },
    {
      name: '平均适应度',
      type: 'line',
      data: data.iterations.map((it, i) => [it, data.avgFitness[i]]),
      smooth: true,
      lineStyle: { color: '#9B8A7A', width: 2, type: 'dashed' },
    },
    {
      name: '中位数适应度',
      type: 'line',
      data: data.iterations.map((it, i) => [it, data.medianFitness[i]]),
      smooth: true,
      lineStyle: { color: '#C4B5A5', width: 1.5 },
    },
  ]
}

/** 从收敛数据构造种群多样性曲线 */
export function buildDiversitySeries(
  data: AOOConvergenceData
): ConvergenceSeriesConfig {
  return {
    name: '种群多样性',
    type: 'line',
    data: data.iterations.map((it, i) => [it, data.diversity[i]]),
    smooth: true,
    lineStyle: { color: '#FF8C42', width: 2 },
    areaStyle: { color: '#FF8C42', opacity: 0.12 },
  }
}

/** 将种群快照转换为散点图动画帧 */
export function buildPopulationFrames(
  data: AOOConvergenceData
): PopulationFrame[] {
  if (!data.populationSnapshots) return []

  return data.populationSnapshots.map((snapshot, index) => ({
    currentIteration: data.iterations[index],
    data: snapshot.positionsX.map((x, i) => [x, snapshot.positionsY[i]]),
    bestPoint: [
      snapshot.positionsX[snapshot.bestIndex],
      snapshot.positionsY[snapshot.bestIndex],
    ],
    diversity: data.diversity[index],
  }))
}
