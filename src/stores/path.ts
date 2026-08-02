import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  LearningPath,
  LearningTask,
  AlternativePath,
  TaskStatus,
  GanttTask,
  DailyTaskView
} from '@/types'
import type { AOOConvergenceData } from '@/types/aoo'
import { pathApi } from '@/api/modules/path'
import { message } from 'ant-design-vue'
import { trackEvent } from '@/utils/tracking'

/** AOO 任务轮询间隔（毫秒） */
const POLL_INTERVAL = 2000
/** 最大轮询次数（2秒 * 150 = 300秒 = 5分钟超时） */
const MAX_POLL_COUNT = 150

/**
 * 学习路径状态管理
 *
 * 职责：
 * - 触发 AOO 异步生成学习路径
 * - 轮询任务状态直到完成
 * - 管理当前路径 / 备选路径
 * - 提供甘特图 & 每日任务视图派生数据
 *
 * 闭环流程：
 *   diagnoseStore.submitDiagnosis() 成功
 *   → router.push('/path')
 *   → PathView.onMounted 读取 diagnoseStore.currentDiagnosis
 *   → pathStore.generatePath(diagnosisId)
 *   → 轮询 AOO task status
 *   → completed → 渲染路径
 */
export const usePathStore = defineStore(
  'path',
  () => {
    // ═══════════ State ═══════════

    /** 当前选中的学习路径 */
    const currentPath = ref<LearningPath | null>(null)

    /** 备选路径方案 */
    const alternativePaths = ref<AlternativePath[]>([])

    /** AOO 异步任务 ID */
    const taskId = ref<string | null>(null)

    /** AOO 优化状态 */
    const optimizationStatus = ref<TaskStatus>('idle')

    /** 生成进度 0-100 */
    const generationProgress = ref(0)

    /** 是否正在生成 */
    const isGenerating = ref(false)

    /** 错误信息 */
    const error = ref<string | null>(null)

    /** AOO 收敛数据（供回放可视化使用） */
    const convergenceData = ref<AOOConvergenceData | null>(null)

    /** 轮询定时器 ID（用于清理） */
    let _pollTimer: ReturnType<typeof setTimeout> | null = null

    /** 当前轮询计数 */
    let _pollCount = 0

    /** 路径生成起始时间戳（仅用于埋点统计耗时） */
    let _generateStartedAt = 0

    // ═══════════ Getters ═══════════

    /** 是否有当前路径 */
    const hasPath = computed(() => currentPath.value !== null)

    /** 是否有备选路径 */
    const hasAlternatives = computed(() => alternativePaths.value.length > 0)

    /** 路径 ID */
    const pathId = computed(() => currentPath.value?.id ?? null)

    /** 当前任务数量 */
    const taskCount = computed(() => currentPath.value?.totalTasks ?? 0)

    /** 总学习天数 */
    const totalDays = computed(() => currentPath.value?.totalDays ?? 0)

    /** 预估总学习时长（小时） */
    const estimatedHours = computed(() => currentPath.value?.totalEstimatedHours ?? 0)

    /** 每日任务视图 */
    const dailyTaskViews = computed<DailyTaskView[]>(() => {
      if (!currentPath.value) return []
      // 防御：持久化数据可能格式不兼容
      if (!Array.isArray(currentPath.value.dailyTasks)) return []

      const today = new Date()

      return currentPath.value.dailyTasks.map((tasks, index) => {
        const totalMinutes = tasks.reduce((sum, t) => sum + t.estimatedMinutes, 0)
        const avgDifficulty =
          tasks.length > 0
            ? Math.round(
                (tasks.reduce((sum, t) => sum + t.difficulty, 0) / tasks.length) * 10
              ) / 10
            : 0

        const date = new Date(today)
        date.setDate(date.getDate() + index)

        return {
          dayIndex: index + 1,
          dayLabel: `第 ${index + 1} 天`,
          date: date.toLocaleDateString('zh-CN', {
            month: 'short',
            day: 'numeric',
            weekday: 'short'
          }),
          tasks,
          totalMinutes,
          difficulty: avgDifficulty
        }
      })
    })

    /** 甘特图数据 */
    const ganttData = computed<GanttTask[]>(() => {
      if (!currentPath.value) return []
      if (!Array.isArray(currentPath.value.dailyTasks)) return []

      const result: GanttTask[] = []
      let globalTaskId = 0

      currentPath.value.dailyTasks.forEach((tasks, dayIndex) => {
        // 每天从 8:00 开始排列
        let hourOffset = 8

        tasks.forEach((task) => {
          const durationHours = task.estimatedMinutes / 60
          result.push({
            id: `task-${++globalTaskId}`,
            name: task.title,
            day: dayIndex + 1,
            startHour: hourOffset,
            durationHours: Math.max(durationHours, 0.25), // 最少 15 分钟
            difficulty: task.difficulty,
            knowledgePoint: task.knowledgePoint
          })
          hourOffset += durationHours + 0.25 // 任务间休息 15 分钟
        })
      })

      return result
    })

    /** 难度曲线（折线图） */
    const difficultyCurve = computed(() => currentPath.value?.difficultyCurve ?? [])

    /** 算法优化得分 */
    const optimizationScore = computed(
      () => currentPath.value?.metadata?.optimizationScore ?? 0
    )

    /** 路径生成耗时 */
    const generationTime = computed(() => currentPath.value?.metadata?.generationTime ?? 0)

    /** 是否有 AOO 收敛数据 */
    const hasConvergenceData = computed(() => convergenceData.value !== null)

    // ═══════════ Actions ═══════════

    /**
     * 触发 AOO 异步生成学习路径
     *
     * @param diagnosisId 诊断结果 ID
     * @returns 是否成功触发
     */
    async function generatePath(
      diagnosisId: string
    ): Promise<boolean> {
      // 防止重复触发
      if (isGenerating.value && optimizationStatus.value !== 'idle') {
        message.warning('路径正在生成中，请耐心等待')
        return false
      }

      isGenerating.value = true
      optimizationStatus.value = 'pending'
      generationProgress.value = 0
      error.value = null
      _generateStartedAt = Date.now()
      trackEvent('path_generate_start', { diagnosisId })

      try {
        // 1. 提交生成请求（异步任务）
        // 后端根据 diagnosis 自动补全 mastery_levels, student_id 等字段
        const response = await pathApi.generate({
          diagnosisId,
        } as any)

        taskId.value = response.taskId
        optimizationStatus.value = 'queued'
        generationProgress.value = 5

        const estimatedSeconds = (response as any).estimatedSeconds || 30
        message.info(`AOO 引擎已启动，预计 ${estimatedSeconds} 秒完成分析`)

        // 2. 开始轮询任务状态
        startPolling()

        return true
      } catch (e) {
        isGenerating.value = false
        optimizationStatus.value = 'failed'
        error.value = '路径生成失败，请稍后重试'
        console.error('[PathStore] 触发路径生成失败:', e)
        return false
      }
    }

    /**
     * 灵活重规划（基于任意历史诊断 / 诊断 + 当前对话画像）
     *
     * @param diagnosisId 任意一次历史诊断 ID（基底）
     * @param useChatProfile 是否叠加当前「智能问答对话画像」(mode='diagnosis+chat')
     *
     * 复用与 generatePath 相同的轮询闭环；不同点在于基底来源可在诊断与对话之间组合。
     */
    async function regeneratePathFlexible(
      diagnosisId: string,
      useChatProfile: boolean = false
    ): Promise<boolean> {
      if (isGenerating.value && optimizationStatus.value !== 'idle') {
        message.warning('路径正在生成中，请耐心等待')
        return false
      }

      isGenerating.value = true
      optimizationStatus.value = 'pending'
      generationProgress.value = 0
      error.value = null
      _generateStartedAt = Date.now()
      trackEvent('path_regenerate_flexible', { diagnosisId, useChatProfile })

      try {
        const response = await pathApi.optimizeFlexible(diagnosisId, useChatProfile) as any

        taskId.value = response.taskId || response.task_id || null
        if (!taskId.value) {
          throw new Error('后端未返回任务 ID')
        }
        optimizationStatus.value = 'queued'
        generationProgress.value = 5
        message.info(
          useChatProfile
            ? '已基于「诊断 + 对话分析」启动重规划'
            : '已基于所选诊断启动重规划'
        )

        startPolling()
        return true
      } catch (e: any) {
        isGenerating.value = false
        optimizationStatus.value = 'failed'
        error.value = '重规划启动失败，请稍后重试'
        const detail =
          e?.response?.data?.detail ?? e?.response?.data?.message ?? e?.message
        console.error('[PathStore] 灵活重规划失败:', e)
        message.error(detail ? `重规划失败：${detail}` : '重规划失败，请稍后重试')
        return false
      }
    }

    /** 开始轮询 AOO 任务状态 */
    function startPolling(): void {
      stopPolling()
      _pollCount = 0
      _poll()
    }

    /** 单次轮询 */
    async function _poll(): Promise<void> {
      if (!taskId.value) return

      _pollCount++

      // 超时保护
      if (_pollCount > MAX_POLL_COUNT) {
        optimizationStatus.value = 'failed'
        isGenerating.value = false
        error.value = '路径生成超时，请稍后重试或联系管理员'
        message.error('路径生成超时')
        return
      }

      try {
        const status = await pathApi.getTaskStatus(taskId.value)

        switch (status.status) {
          case 'completed':
            // 生成完成
            optimizationStatus.value = 'completed'
            isGenerating.value = false
            generationProgress.value = 100

            if (status.result) {
              _applyResult(status.result as unknown as Record<string, unknown>)
            }

            trackEvent('path_generate_complete', {
              success: true,
              durationMs: _generateStartedAt ? Date.now() - _generateStartedAt : 0,
              taskCount: currentPath.value?.totalTasks ?? 0
            })

            message.success('学习路径生成完毕！查看你的专属学习计划')
            stopPolling()
            break

          case 'failed':
            optimizationStatus.value = 'failed'
            isGenerating.value = false
            error.value = status.errorMessage || 'AOO 引擎处理失败'
            trackEvent('path_generate_complete', {
              success: false,
              durationMs: _generateStartedAt ? Date.now() - _generateStartedAt : 0
            })
            message.error('路径生成失败')
            stopPolling()
            break

          case 'processing': {
            optimizationStatus.value = 'processing'
            // 后端 AOOTaskStatusResponse.progress 的单位是 0~1（不是百分比），
            // 这里统一归一化为 0~100 的百分比再驱动进度条。
            // 兼容性处理：若后端未来改回 0~100，>1 的值按百分比直接使用。
            const raw = Number(status.progress) || 0
            const percent = raw <= 1 ? raw * 100 : raw
            // 进度条只增不减，避免因后端回退导致动画倒退
            generationProgress.value = Math.max(
              generationProgress.value,
              Math.min(percent, 95)
            )
            // 继续轮询
            _pollTimer = setTimeout(_poll, POLL_INTERVAL)
            break
          }

          case 'pending':
          case 'queued':
            optimizationStatus.value = status.status
            // 无进度时的动画效果: 缓慢增长到 ~15% 单次最大 1s 轮询期间的增量
            generationProgress.value = Math.min(
              generationProgress.value + 3,
              15
            )
            // 继续轮询
            _pollTimer = setTimeout(_poll, POLL_INTERVAL)
            break
        }
      } catch (e) {
        console.error('[PathStore] 轮询任务状态失败:', e)
        // 网络错误时不立即失败，继续重试
        if (_pollCount <= MAX_POLL_COUNT) {
          _pollTimer = setTimeout(_poll, POLL_INTERVAL * 2) // 错误时延长间隔
        } else {
          optimizationStatus.value = 'failed'
          isGenerating.value = false
          error.value = '获取生成状态失败，请刷新页面重试'
        }
      }
    }

    /** 停止轮询 */
    function stopPolling(): void {
      if (_pollTimer) {
        clearTimeout(_pollTimer)
        _pollTimer = null
      }
    }

    /**
     * 将 AOO 引擎返回的原始结果转换为 LearningPath 格式。
     *
     * 注意：后端任务状态端点（AOOTaskStatusResponse.result）的真实类型是
     * AOOOptimizeResult，其 JSON 结构为：
     *   {
     *     bestPath:      { days: PathDay[], totalDays, totalTasks, totalEstimatedHours, totalFitness },
     *     convergenceData: AOOConvergenceData,   ← 字段名不是 convergence！
     *     alternativePaths: AlternativePath_BE[], ← 嵌套在 result 内部，不在顶层
     *     fitnessDetail, paretoFront, executionTime  ← 前端未使用
     *   }
     *
     * 此函数负责将所有 data 转换为前端 LearningPath + convergenceData + alternativePaths。
     */
    function _applyResult(raw: any): void {
      const bp = raw.bestPath as any | undefined
      if (!bp) return

      // 按天构建 dailyTasks: LearningTask[][]
      const days = (bp.days || []) as any[]
      const dailyTasks: LearningTask[][] = days.map((day) => {
        return ((day.tasks || []) as any[]).map((task, order): LearningTask => ({
          id: `task-${day.day}-${order}`,
          dayIndex: day.day as number,
          orderIndex: order + 1,
          title: (task.name || task.kp_name || task.knowledgePoint || task.knowledge_point || '') as string,
          description: `学习 ${(task.name || task.kp_name || task.knowledgePoint || task.knowledge_point || '')}`,
          knowledgePoint: (task.knowledgePoint || task.knowledge_point || '') as string,
          estimatedMinutes: (task.duration || 15) as number,
          difficulty: (task.difficulty || 1) as LearningTask['difficulty'],
          resources: (task.resources || []) as any[],
        }))
      })

      const difficultyCurve = days.map((d) => (d.avgDifficulty ?? d.avg_difficulty ?? 1) as number)

      currentPath.value = {
        id: taskId.value || '',
        taskId: taskId.value || '',
        diagnosisId: (raw.diagnosisId || raw.diagnosis_id || '') as string,
        userId: '',
        createdAt: new Date().toISOString(),
        totalDays: (bp.totalDays || bp.total_days || 0) as number,
        totalTasks: (bp.totalTasks || bp.total_tasks || 0) as number,
        totalEstimatedHours: (bp.totalEstimatedHours || bp.total_estimated_hours || 0) as number,
        difficultyCurve,
        dailyTasks,
        metadata: {
          algorithm: 'AOO',
          optimizationScore: Math.round(((bp.totalFitness || bp.total_fitness || 0) as number) * 100),
          generationTime: 0,
        },
      }

      // 收敛数据：后端 AOOTaskStatusResponse.result 的真实字段是 convergenceData
      const convergence = (raw.convergenceData || raw.convergence_data || raw.convergence) as AOOConvergenceData | undefined
      if (convergence?.iterations?.length) {
        convergenceData.value = convergence
      }

      // 备选路径：后端 AOOOptimizeResult 中嵌套为 result.alternativePaths，
      // 前端之前误从顶层 status.alternativePaths 读取，现统一在此处理
      const rawAlts = (raw.alternativePaths || raw.alternative_paths) as any[] | undefined
      if (rawAlts?.length) {
        alternativePaths.value = rawAlts.map(_transformAlternativePath)
      }
    }

    /**
     * 将后端 AOOOptimizeResult.alternative_paths 中的单条备选路径
     * （{ pathType, days: PathDay[], totalDays, totalTasks, totalEstimatedHours, fitness }）
     * 转换为前端 AlternativePath 格式（含 dailyTasks: LearningTask[][] 等）。
     */
    function _transformAlternativePath(raw: any): AlternativePath {
      const days = (raw.days || []) as any[]
      const dailyTasks: LearningTask[][] = days.map((day) => {
        return ((day.tasks || []) as any[]).map((task, order): LearningTask => ({
          id: `alt-${day.day}-${order}`,
          dayIndex: day.day as number,
          orderIndex: order + 1,
          title: (task.name || task.kp_name || '') as string,
          description: `学习 ${(task.name || task.kp_name || '')}`,
          knowledgePoint: (task.knowledgePoint || task.knowledge_point || '') as string,
          estimatedMinutes: (task.duration || 15) as number,
          difficulty: (task.difficulty || 1) as LearningTask['difficulty'],
          resources: (task.resources || []) as any[],
        }))
      })

      // 根据 pathType 映射前端 label / description
      // 注意：label 必须与 PathView.vue 的 variantLabels 一致
      //（['当前方案', '速成冲刺', '稳扎稳打', '查漏补缺']）
      const pathType = (raw.pathType || raw.path_type || 'balanced') as string
      const typeLabelMap: Record<string, { type: AlternativePath['type']; label: string; description: string }> = {
        efficiency: { type: 'intensive', label: '速成冲刺', description: '最短时间覆盖最多知识点，适合考前突击' },
        balanced:   { type: 'balanced',  label: '稳扎稳打', description: '学习效果与认知负荷的最佳平衡' },
        robust:     { type: 'light',     label: '查漏补缺', description: '低负荷、高巩固，聚焦薄弱点逐个击破' },
      }
      const meta = typeLabelMap[pathType] || typeLabelMap['balanced']

      return {
        // id 必须稳定：PathView 通过 id 调用 selectAlternativePath，
        // 使用 Date.now() 会导致每次转换后 id 变化、切换失效。
        id: (raw.id as string) || `alt-${pathType}`,
        taskId: (raw.taskId || '') as string,
        type: meta!.type,
        label: meta!.label,
        description: meta!.description,
        totalDays: (raw.totalDays || raw.total_days || 0) as number,
        totalTasks: (raw.totalTasks || raw.total_tasks || 0) as number,
        totalEstimatedHours: (raw.totalEstimatedHours || raw.total_estimated_hours || 0) as number,
        dailyTasks,
        highlights: [],
        targetAudience: '',
        philosophy: '',
        features: [],
      }
    }

    /** 从 API 获取当前活跃路径（页面刷新恢复） */
    async function fetchCurrentPath(): Promise<void> {
      try {
        const path = await pathApi.getCurrentPath()
        if (path) {
          // 防御：若 API 返回的路径缺少必要字段，视为无效
          if (!Array.isArray(path.dailyTasks)) {
            console.warn('[PathStore] 路径数据格式不兼容，已清除')
            clearPath()
            return
          }
          currentPath.value = path
          optimizationStatus.value = 'completed'
          taskId.value = path.taskId

          // 页面刷新恢复：备选方案与寻优回放数据随路径记录一并下发，
          // 这里必须回填，否则「速成冲刺 / 稳扎稳打 / 查漏补缺」标签页
          // 和收敛回放图在刷新后会消失。
          const rawAlts = (path as any).alternativePaths as any[] | undefined
          if (rawAlts?.length) {
            alternativePaths.value = rawAlts.map(_transformAlternativePath)
          }
          const conv = (path as any).convergenceData as AOOConvergenceData | undefined
          if (conv?.iterations?.length) {
            convergenceData.value = conv
          }
        } else {
          // API 返回 null（无路径），清除可能的过期持久化数据
          clearPath()
        }
      } catch (e) {
        console.warn('[PathStore] 获取当前路径失败:', e)
        // 请求失败时也清除可能的过期数据
        clearPath()
      }
    }

    /** 根据 ID 获取指定路径 */
    async function fetchPath(id: string): Promise<LearningPath | null> {
      try {
        const path = await pathApi.getPath(id)
        currentPath.value = path
        return path
      } catch (e) {
        console.error('[PathStore] 获取路径详情失败:', e)
        return null
      }
    }

    /** 选择备选路径方案 */
    async function selectAlternativePath(pathId: string): Promise<boolean> {
      try {
        await pathApi.selectPath(pathId)
        const selected = alternativePaths.value.find((p) => p.id === pathId)
        trackEvent('path_select', { pathId, pathType: selected?.type ?? '' })
        if (selected && currentPath.value) {
          // 从备选路径的 dailyTasks 重新计算 difficultyCurve
          const difficultyCurve = selected.dailyTasks.map((day) => {
            if (day.length === 0) return 1
            return Math.round(day.reduce((s, t) => s + t.difficulty, 0) / day.length)
          })

          // 将备选方案提升为当前路径
          currentPath.value = {
            ...currentPath.value,
            id: selected.id,
            totalDays: selected.totalDays,
            totalTasks: selected.totalTasks,
            totalEstimatedHours: selected.totalEstimatedHours,
            dailyTasks: selected.dailyTasks,
            difficultyCurve,
            metadata: {
              algorithm: 'AOO',
              optimizationScore: 0,  // 备选路径无原始收敛数据
              generationTime: 0,
            },
          }

          message.success('已切换到新方案')
          return true
        }
        return false
      } catch (e) {
        console.error('[PathStore] 切换备选路径失败:', e)
        // 之前静默失败，用户点击后毫无反馈，这里明确提示后端返回的原因
        const detail =
          (e as { response?: { data?: { detail?: string; message?: string } } })
            ?.response?.data?.detail ??
          (e as { response?: { data?: { message?: string } } })?.response?.data
            ?.message
        message.error(detail ? `切换方案失败：${detail}` : '切换方案失败，请稍后重试')
        return false
      }
    }

    /** 获取备选方案列表（速成冲刺 / 稳扎稳打 / 查漏补缺） */
    async function fetchAlternatives(): Promise<void> {
      if (!taskId.value) return
      try {
        const alts = await pathApi.getAlternatives(taskId.value)
        // 后端返回的是 AOO 原始结构（pathType/days/...），
        // 必须经过 _transformAlternativePath 才能被 UI 渲染。
        if (Array.isArray(alts) && alts.length) {
          alternativePaths.value = alts.map(_transformAlternativePath)
        }
      } catch (e) {
        console.error('[PathStore] 获取备选路径失败:', e)
      }
    }

    /** 加载路径历史 */
    async function fetchHistory(): Promise<LearningPath[]> {
      try {
        return await pathApi.getHistory()
      } catch (e) {
        console.error('[PathStore] 获取路径历史失败:', e)
        return []
      }
    }

    /** 删除指定路径 */
    async function deletePath(id: string): Promise<boolean> {
      try {
        await pathApi.deletePath(id)
        if (currentPath.value?.id === id) {
          currentPath.value = null
          optimizationStatus.value = 'idle'
          taskId.value = null
        }
        message.success('路径已删除')
        return true
      } catch (e) {
        console.error('[PathStore] 删除路径失败:', e)
        return false
      }
    }

    /** 清除当前路径 */
    function clearPath(): void {
      stopPolling()
      currentPath.value = null
      alternativePaths.value = []
      convergenceData.value = null
      taskId.value = null
      optimizationStatus.value = 'idle'
      generationProgress.value = 0
      isGenerating.value = false
      error.value = null
      _pollCount = 0
    }

    /** 清理（组件卸载时调用） */
    function dispose(): void {
      stopPolling()
    }

    return {
      // State
      currentPath,
      alternativePaths,
      taskId,
      optimizationStatus,
      generationProgress,
      isGenerating,
      error,
      convergenceData,
      // Getters
      hasPath,
      hasAlternatives,
      hasConvergenceData,
      pathId,
      taskCount,
      totalDays,
      estimatedHours,
      dailyTaskViews,
      ganttData,
      difficultyCurve,
      optimizationScore,
      generationTime,
      // Actions
      generatePath,
      regeneratePathFlexible,
      fetchCurrentPath,
      fetchPath,
      selectAlternativePath,
      fetchAlternatives,
      fetchHistory,
      deletePath,
      clearPath,
      dispose
    }
  },
  {
    persist: {
      key: 'oat_path_store',
      storage: localStorage,
      // 持久化路径结果，但不保存生成中的瞬时状态
      paths: ['currentPath', 'alternativePaths', 'taskId']
    }
  }
)
