import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  LearningPath,
  LearningTask,
  AlternativePath,
  GeneratePathRequest,
  TaskStatus,
  GanttTask,
  DailyTaskView
} from '@/types'
import type { AOOConvergenceData } from '@/types/aoo'
import { pathApi } from '@/api/modules/path'
import { message } from 'ant-design-vue'

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
     * @param preferences  偏好设置（最大天数、重点领域、学习强度）
     * @returns 是否成功触发
     */
    async function generatePath(
      diagnosisId: string,
      preferences?: GeneratePathRequest['preferences']
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

      try {
        // 1. 提交生成请求（异步任务）
        const response = await pathApi.generate({
          diagnosisId,
          preferences
        })

        taskId.value = response.taskId
        optimizationStatus.value = 'queued'
        generationProgress.value = 5

        message.info(`AOO 引擎已启动，预计 ${response.estimatedSeconds} 秒完成分析`)

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
              currentPath.value = status.result as unknown as LearningPath
              // 尝试保存 AOO 收敛数据（若 API 返回）
              const result = status.result as Record<string, unknown>
              if (result.convergence) {
                convergenceData.value = result.convergence as AOOConvergenceData
              }
            }
            if (status.alternativePaths) {
              alternativePaths.value = status.alternativePaths
            }

            message.success('学习路径生成完毕！查看你的专属学习计划')
            stopPolling()
            break

          case 'failed':
            optimizationStatus.value = 'failed'
            isGenerating.value = false
            error.value = status.errorMessage || 'AOO 引擎处理失败'
            message.error('路径生成失败')
            stopPolling()
            break

          case 'processing':
            optimizationStatus.value = 'processing'
            generationProgress.value = Math.min(status.progress, 95)
            // 继续轮询
            _pollTimer = setTimeout(_poll, POLL_INTERVAL)
            break

          case 'pending':
          case 'queued':
            optimizationStatus.value = status.status
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
        if (selected) {
          // 将备选方案提升为当前路径
          currentPath.value = {
            ...currentPath.value!,
            ...selected,
            id: selected.id
          } as unknown as LearningPath
          message.success('已切换到新方案')
          return true
        }
        return false
      } catch (e) {
        console.error('[PathStore] 切换备选路径失败:', e)
        return false
      }
    }

    /** 获取备选方案列表 */
    async function fetchAlternatives(): Promise<void> {
      if (!taskId.value) return
      try {
        const alts = await pathApi.getAlternatives(taskId.value)
        alternativePaths.value = alts
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
      pick: ['currentPath', 'alternativePaths', 'taskId']
    }
  }
)
