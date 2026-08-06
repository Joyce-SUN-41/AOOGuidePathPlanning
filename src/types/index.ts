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

// ============= 学情测绘相关 =============

/** 测绘题目的选项 */
export interface CehuiOption {
  id: string
  text: string
  weight: number // 0-1 掌握度权重
}

/** 测绘题目 */
export interface CehuiQuestion {
  id: string
  topic: string // 所属知识点
  difficulty: 1 | 2 | 3 | 4 | 5
  title: string
  options: CehuiOption[]
  type: 'single' | 'multiple' | 'judge'
}

/** 用户提交的答案 */
export interface CehuiAnswer {
  questionId: string
  /** 用户选择的选项 ID（单选）。
   *  后端 SubmittedAnswer.selected_option 为单个字符串，
   *  此前误定义为 selectedOptionIds: string[]，导致提交字段对不上。 */
  selectedOption: string
  timeSpent: number // 答题耗时(秒)
}

/** 学习风格自陈单项 */
export interface StyleItem {
  key: string
  value: number // likert 1-5
}

/** 学习准备度自陈单项 */
export interface ReadinessItem {
  key: string
  value: number // likert 1-5
}

/** 学习准备度画像（第三维自变量，0-1 归一化） */
export interface ReadinessProfile {
  motivation: number
  metacognition: number
  selfEfficacy: number
  rawItems?: ReadinessItem[]
}

/** 测绘提交请求体（三维度综合） */
export interface CehuiSubmitRequest {
  answers: CehuiAnswer[]
  subject?: string // 学科
  grade?: string // 年级
  /** 第二维: 学习风格自陈题项（key/value 1-5） */
  styleItems?: StyleItem[]
  /** 第三维: 学习准备度画像（motivation/metacognition/selfEfficacy 0-1 + 原始题项） */
  readiness?: ReadinessProfile
}

/** 知识点掌握度 */
export interface MasteryItem {
  knowledgePoint: string
  kpId?: string
  mastery: number // 0-1 点估计
  level: 'weak' | 'developing' | 'proficient' | 'excellent'
  confidence: number // 0-1 置信度
  /** 条目1: 掌握度 95% 经验置信区间 [low, high]（题量不足时区间较宽） */
  confidenceInterval?: [number, number] | null
  /** 该知识点本次作答题数，用于判断样本充分性 */
  nQuestions?: number
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

/** 学习风格画像（第四项维度展示用） */
export interface LearningStyleProfile {
  /** 主风格标签（进取型/顺序型/踏实型/探索型） */
  label: string
  /** 四风格维度归一化得分 0-1 */
  scores: Record<string, number>
  /** 条目4/6: 主导风格 key（如 exploratory）；全 0 时为 undefined */
  primaryDimension?: string | null
  /** 辅助风格 key（得分次高维度） */
  secondaryDimension?: string | null
  /** 风格强度 = 主导分 - 次高分（0-1）；越低越混合/不明显 */
  intensity?: number | null
}

/** 学习准备度画像（第三维展示用） */
export interface ReadinessProfileResult {
  motivation: number
  metacognition: number
  selfEfficacy: number
  /** 条目9: 学科特异性自我效能 {kp_id: 0-1}（代理估计，需说明） */
  efficacyByKp?: Record<string, number> | null
  /** 条目8: 纵向趋势（本次-上次） */
  trend?: { motivation: number; metacognition: number; selfEfficacy: number } | null
}

/** 测绘结果 */
export interface CehuiResult {
  id: string
  userId: string
  createdAt: string
  subject: string
  grade: string

  /** 各知识点掌握度（维度一：知识层面） */
  masteryLevels: MasteryItem[]

  /** 认知负荷分析 */
  cognitiveLoad: CognitiveLoadProfile

  /** 学习风格标签（兼容旧字段） */
  learningStyle: string

  /** 学习风格画像（维度二：学习风格层面） */
  learningStyleProfile?: LearningStyleProfile | null

  /** 学习准备度画像（维度三：学习准备度层面） */
  readinessProfile?: ReadinessProfileResult | null

  /** 薄弱点列表 */
  weakPoints: WeakPoint[]

  /** 综合评分 (雷达图用) */
  overallScore: number // 0-100

  /** AI 测绘摘要（旧字段，兼容） */
  summary: string

  /** 条目10: 维度间交叉洞察（规则生成，无 LLM） */
  crossInsights?: string[]

  /** 条目11: 量表与计分方式说明 */
  scaleNote?: string

  /** 条目14: 规则生成的 AI 自然语言摘要 */
  aiSummary?: string
}

/** 测绘历史简要 */
export interface CehuiBrief {
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

  /** 版本号（首轮=1，回流重规划=parent+1） */
  version?: number
  /** 规划类型语义标签（建议 11）: baseline=起点规划, update_vN=动态更新第N版; 旧路径为空 */
  planType?: string | null

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
  totalCehuis: number
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
  cehuiCount: number
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

