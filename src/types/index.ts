// ============= 通用类型 =============

/** API 通用响应结构 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

/** 分页请求参数 */
export interface PaginationParams {
  page: number
  pageSize: number
}

/** 分页响应数据 */
export interface PaginatedData<T> {
  list: T[]
  total: number
  page: number
  pageSize: number
}

/** 通用下拉选项 */
export interface SelectOption {
  label: string
  value: string | number
  disabled?: boolean
}

// ============= 角色类型 =============

/** 用户角色 */
export type UserRole = 'student' | 'teacher'

/** 角色列表 */
export const USER_ROLES: Record<UserRole, string> = {
  student: '学生',
  teacher: '教师'
}

// ============= 用户相关 =============

/** 用户信息 */
export interface UserInfo {
  id: string
  username: string
  nickname: string
  avatar?: string
  email?: string
  phone?: string
  role: UserRole
  status: 0 | 1
  createTime: string
}

/** 登录请求参数 */
export interface LoginParams {
  username: string
  password: string
  remember?: boolean
}

/** 注册请求参数 */
export interface RegisterParams {
  username: string
  password: string
  confirmPassword: string
  nickname: string
  email?: string
  role: UserRole
}

/** 登录返回结果 */
export interface LoginResult {
  token: string
  userInfo: UserInfo
  /** 刷新令牌 (后端 AuthResponse.refreshToken)，用于 access token 过期时静默续期 */
  refreshToken?: string
}

// ============= 路由相关 =============

/** 路由 Meta 类型 */
export interface RouteMeta {
  title?: string
  icon?: string
  hidden?: boolean
  keepAlive?: boolean
  /** 允许访问的角色列表，空数组或不设置表示所有已登录用户可访问 */
  roles?: UserRole[]
}

// ============= 图表相关 =============

/** 图表数据项 */
export interface ChartDataItem {
  name: string
  value: number
}

// ============= 认知诊断相关 =============

/** 诊断题目的选项 */
export interface DiagnosisOption {
  id: string
  text: string
  weight: number // 0-1 掌握度权重
}

/** 诊断题目 */
export interface DiagnosisQuestion {
  id: string
  topic: string // 所属知识点
  difficulty: 1 | 2 | 3 | 4 | 5
  title: string
  options: DiagnosisOption[]
  type: 'single' | 'multiple'
}

/** 用户提交的答案 */
export interface DiagnosisAnswer {
  questionId: string
  /** 用户选择的选项 ID（单选）。
   *  后端 SubmittedAnswer.selected_option 为单个字符串，
   *  此前误定义为 selectedOptionIds: string[]，导致提交字段对不上。 */
  selectedOption: string
  timeSpent: number // 答题耗时(秒)
}

/** 诊断提交请求体 */
export interface DiagnosisSubmitRequest {
  answers: DiagnosisAnswer[]
  subject?: string // 学科
  grade?: string // 年级
}

/** 知识点掌握度 */
export interface MasteryItem {
  knowledgePoint: string
  mastery: number // 0-1
  level: 'weak' | 'developing' | 'proficient' | 'excellent'
  confidence: number // 0-1 置信度
}

/** 认知负荷维度 */
export interface CognitiveLoadProfile {
  memoryLoad: number // 记忆负荷 0-1
  attentionLoad: number // 注意力负荷 0-1
  processingLoad: number // 加工负荷 0-1
  overall: number // 综合负荷 0-1
}

/** 薄弱点 */
export interface WeakPoint {
  knowledgePoint: string
  reason: string
  severity: 'mild' | 'moderate' | 'severe'
  suggestedRemediation?: string
}

/** 诊断结果 */
export interface DiagnosisResult {
  id: string
  userId: string
  createdAt: string
  subject: string
  grade: string

  /** 各知识点掌握度 */
  masteryLevels: MasteryItem[]

  /** 认知负荷分析 */
  cognitiveLoad: CognitiveLoadProfile

  /** 学习风格标签 */
  learningStyle: string

  /** 薄弱点列表 */
  weakPoints: WeakPoint[]

  /** 综合评分 (雷达图用) */
  overallScore: number // 0-100

  /** AI 诊断摘要 */
  summary: string
}

/** 诊断历史简要 */
export interface DiagnosisBrief {
  id: string
  createdAt: string
  subject: string
  overallScore: number
  weakPointCount: number
}

// ============= 学习路径相关 =============

/** AOO 任务状态 */
export type TaskStatus =
  | 'idle'
  | 'pending'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'

/** 单个学习任务 */
export interface LearningTask {
  id: string
  dayIndex: number // 第几天
  orderIndex: number // 当天第几个任务
  title: string
  description: string
  knowledgePoint: string
  estimatedMinutes: number
  difficulty: 1 | 2 | 3 | 4 | 5

  /** 学习资源 */
  resources: {
    type: 'video' | 'article' | 'exercise' | 'project' | 'quiz'
    title: string
    url?: string
  }[]
}

/** 学习路径 */
export interface LearningPath {
  id: string
  taskId: string
  diagnosisId: string
  userId: string
  createdAt: string

  /** 路径总览 */
  totalDays: number
  totalTasks: number
  totalEstimatedHours: number
  difficultyCurve: number[] // 每天的平均难度

  /** 每日任务 */
  dailyTasks: LearningTask[][]

  /** 路径元信息 */
  metadata: {
    algorithm: string // 'AOO'
    optimizationScore: number // 优化得分 0-100
    generationTime: number // 生成耗时(秒)
  }
}

/** 备选学习路径（用于对比选择） */
export interface AlternativePath {
  id: string
  taskId: string
  /** 方案名称：速成冲刺 / 稳扎稳打 / 查漏补缺 */
  label: string
  /** 方案类型，对应后端 pathType: efficiency / balanced / robust */
  type?: 'intensive' | 'balanced' | 'light'
  description: string
  totalDays: number
  totalTasks: number
  totalEstimatedHours: number
  highlights: string[] // 方案亮点
  dailyTasks: LearningTask[][]
  /** 适用人群，如「考前冲刺的学生」 */
  targetAudience?: string
  /** 方案理念一句话说明 */
  philosophy?: string
  /** 方案特性标签 */
  features?: string[]
}

/** AOO 生成路径请求 — 请优先使用 aoo.ts 中的 AOOGenerateRequest */
export interface GeneratePathRequest {
  diagnosisId: string
  preferences?: {
    maxDays?: number
    focusAreas?: string[] // 重点关注的薄弱知识点
    intensity?: 'light' | 'moderate' | 'intensive'
  }
}

/** AOO 生成路径响应（异步任务） */
export interface GeneratePathResponse {
  taskId: string
  estimatedSeconds: number
}

/** 任务状态轮询响应
 *  result 字段在 AOO 场景下为 AOOLearningPathResult（包含 bestPath + convergence 收敛数据）
 *  请配合 aoo.ts 中的 isOptimizationCompleted() 类型守卫使用
 */
export interface TaskStatusResponse {
  taskId: string
  status: TaskStatus
  /**
   * 任务进度。
   * 注意：后端 AOOTaskStatusResponse.progress 的实际单位是 **0~1**（小数比例），
   * 不是 0~100 的百分比。消费方需自行乘 100 转换，参见 stores/path.ts 的 _poll()。
   */
  progress: number // 0-1（后端原始单位）
  /**
   * 优化完成后的完整结果。
   * 后端字段名为 convergenceData / alternativePaths（camelCase），
   * 回放图与备选方案标签页都依赖此处的数据。
   */
  result?: {
    bestPath?: Record<string, unknown>
    convergenceData?: import('./aoo').AOOConvergenceData
    alternativePaths?: AlternativePath[]
    fitnessDetail?: Record<string, unknown>
    paretoFront?: unknown[]
    executionTime?: number
  }
  /** 顶层收敛快照（仅当前代，不含 iterations，不能用于回放） */
  convergenceData?: Record<string, unknown>
  alternativePaths?: AlternativePath[]
  errorMessage?: string
}

/** 甘特图数据项（前端渲染用） */
export interface GanttTask {
  id: string
  name: string
  day: number
  startHour: number
  durationHours: number
  difficulty: number
  knowledgePoint: string
  completed?: boolean
}

/** 每日任务视图 */
export interface DailyTaskView {
  dayIndex: number
  dayLabel: string // "第 1 天"
  date: string // 日期
  tasks: LearningTask[]
  totalMinutes: number
  difficulty: number // 当天平均难度
}

// ============= 知识点管理相关 =============

/** 知识点 */
export interface KnowledgePoint {
  id: string
  name: string
  description?: string
  subject: string
  difficulty_level: number
  layer?: string
  tags: string[]
  parent_id?: string
  prerequisites: string[]
  created_at?: string
}

/** 知识点详情 (含前后置 + 关联题目数) */
export interface KnowledgePointDetail extends KnowledgePoint {
  dependents: KnowledgePointBrief[]
  question_count: number
}

/** 知识点简要 */
export interface KnowledgePointBrief {
  id: string
  name: string
  subject: string
  difficulty_level: number
  layer?: string
}

/** 知识点创建/更新参数 */
export interface KnowledgePointForm {
  name: string
  description?: string
  subject: string
  difficulty_level: number
  layer?: string
  tags: string[]
  prerequisites: string[]
  parent_id?: string
}

/** 知识图谱边 */
export interface KnowledgeGraphEdge {
  id: string
  source_kp_id: string
  source_name: string
  target_kp_id: string
  target_name: string
  relation_type: string
}

/** 知识图谱 */
export interface KnowledgeGraph {
  nodes: KnowledgePoint[]
  edges: KnowledgeGraphEdge[]
}

// ============= 题库管理相关 =============

/** 题目选项 */
export interface QuestionOption2 {
  id: string
  text: string
  weight: number
}

/** 题库题目 */
export interface QuestionItem {
  id: string
  code: string
  kp_ids: string[]
  kp_names: string[]
  subject: string
  difficulty: number
  type: string
  title: string
  options: QuestionOption2[]
  correct_option_id: string
  expected_time_sec: number
  explanation?: string
  is_active: boolean
  created_at?: string
  updated_at?: string
}

/** 题目创建/更新参数 */
export interface QuestionForm {
  code: string
  kp_ids: string[]
  subject: string
  difficulty: number
  type: string
  title: string
  options: QuestionOption2[]
  correct_option_id: string
  expected_time_sec: number
  explanation?: string
}

/** 题目列表分页响应 */
export interface QuestionListResponse {
  items: QuestionItem[]
  total: number
  page: number
  page_size: number
}

// ============= 学情看板相关 =============

/** 认知负荷趋势数据点 */
export interface CognitiveLoadTrendPoint {
  date: string
  diagnosisId: string
  memoryLoad: number
  attentionLoad: number
  processingLoad: number
  overall: number
  overallScore: number
}

/** 每日学习活动（热力图用） */
export interface DailyActivityItem {
  date: string // 'YYYY-MM-DD'
  studyMinutes: number
  taskCount: number
  knowledgePoints: string[]
}

/** AI 学习建议 */
export interface LearningSuggestion {
  category: 'strength' | 'weakness' | 'tip' | 'warning'
  title: string
  content: string
  priority: number // 1=最高
  relatedKPs?: string[]
}

/** Dashboard 概览聚合数据 */
export interface DashboardOverview {
  totalStudyMinutes: number
  completedTasks: number
  totalTasks: number
  masteredKPs: number
  totalKPs: number
  streakDays: number
  lastStudyDate: string | null
  totalDiagnoses: number
  totalPaths: number
}

// ============= 教师仪表盘相关 =============

/** 学生学情摘要（教师端学生列表用） */
export interface StudentSummary {
  id: string
  name: string
  nickname: string
  avgMastery: number // 0-1
  cognitiveLoad: number // 0-1
  pathCompletion: number // 0-100
  lastActiveDate: string
  completedTasks: number
  totalTasks: number
  weakPointCount: number
  subject?: string
  overallScore?: number
}

/** 班级概览统计 */
export interface ClassOverview {
  totalStudents: number
  avgMastery: number
  avgCognitiveLoad: number
  avgPathCompletion: number
  highLoadCount: number // 认知负荷 > 0.7 的人数
  lowMasteryCount: number // 掌握度 < 0.6 的人数
}

/** 共性薄弱知识点统计 */
export interface WeakKpStat {
  knowledgePoint: string
  studentCount: number // 薄弱学生数
  avgMastery: number // 该知识点全班平均掌握度
}

/** 全班掌握度趋势数据点 */
export interface MasteryTrendPoint {
  date: string
  avgMastery: number
  diagnosisCount: number
}

/** 预警学生信息 */
export interface AlertStudent {
  studentId: string
  name: string
  nickname: string
  avgMastery: number
  cognitiveLoad: number
  reason: 'highLoad' | 'lowMastery' | 'both'
  severity: 'warning' | 'danger'
}

/** 教师仪表盘完整数据 */
export interface TeacherDashboardData {
  overview: ClassOverview
  students: StudentSummary[]
  weakKps: WeakKpStat[]
  masteryTrend: MasteryTrendPoint[]
  alerts: AlertStudent[]
}

/** 学生详情（弹窗/抽屉用）—— 复用现有类型组合 */
export interface StudentDetail {
  summary: StudentSummary
  masteryLevels: MasteryItem[]
  cognitiveLoad: CognitiveLoadProfile
  weakPoints: WeakPoint[]
  overallScore: number
  subject: string
}

// ============= AOO 可视化类型（从 aoo.ts 重导出，统一入口） =============
// 推荐直接从 aoo.ts 导入以保持模块隔离，此处仅提供快捷重导出

export type {
  PopulationSnapshot,
  AOOConvergenceData,
  ConvergenceMetadata,
  PathTaskInDay,
  PathDay,
  BestPath,
  AOOLearningPathResult,
  AOOLearningPathResponse,
  AOOOptimizationStatus,
  ChartPoint,
  ConvergenceSeriesConfig,
  PopulationFrame,
  AOOGenerateRequest,
  AOOPreferences
} from './aoo'

export {
  isOptimizationCompleted,
  isOptimizationFailed,
  isOptimizationRunning,
  buildConvergenceSeries,
  buildDiversitySeries,
  buildPopulationFrames
} from './aoo'

