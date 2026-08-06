import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  CehuiResult,
  CehuiBrief,
  MasteryItem,
  WeakPoint,
  CognitiveLoadProfile
} from '@/types'
import { cehuiApi } from '@/api/modules/cehui'

/**
 * 学情测绘状态管理
 *
 * 职责：
 * - 管理当前测绘结果
 * - 提供掌握度、认知负荷、薄弱点等派生数据
 * - 支持历史测绘查询
 */
export const useCehuiStore = defineStore(
  'cehui',
  () => {
    // ═══════════ State ═══════════

    /** 当前最新测绘结果 */
    const currentCehui = ref<CehuiResult | null>(null)

    /** 测绘历史列表 */
    const historyList = ref<CehuiBrief[]>([])

    /** 加载状态 */
    const isLoading = ref(false)

    /** 错误信息 */
    const error = ref<string | null>(null)

    // ═══════════ Getters ═══════════

    /** 是否有测绘数据 */
    const hasCehui = computed(() => currentCehui.value !== null)

    /** 综合评分 */
    const overallScore = computed(() => currentCehui.value?.overallScore ?? 0)

    /** 知识点掌握度列表 */
    const masteryLevels = computed<MasteryItem[]>(() => {
      if (!currentCehui.value?.masteryLevels) return []
      return currentCehui.value.masteryLevels
    })

    /** 认知负荷 */
    const cognitiveLoad = computed<CognitiveLoadProfile>(() => {
      return (
        currentCehui.value?.cognitiveLoad ?? {
          memoryLoad: 0,
          attentionLoad: 0,
          processingLoad: 0,
          overall: 0
        }
      )
    })

    /** 薄弱点列表 */
    const weakPoints = computed<WeakPoint[]>(() => {
      return currentCehui.value?.weakPoints ?? []
    })

    /** 按严重度排序的薄弱点 */
    const sortedWeakPoints = computed(() => {
      const severityOrder: Record<string, number> = { severe: 0, moderate: 1, mild: 2 }
      return [...weakPoints.value].sort(
        (a, b) => (severityOrder[a.severity] ?? 3) - (severityOrder[b.severity] ?? 3)
      )
    })

    /** 掌握度统计 */
    const masteryStats = computed(() => {
      const levels = masteryLevels.value
      return {
        excellent: levels.filter((m) => m.level === 'excellent').length,
        proficient: levels.filter((m) => m.level === 'proficient').length,
        developing: levels.filter((m) => m.level === 'developing').length,
        weak: levels.filter((m) => m.level === 'weak').length
      }
    })

    /** 雷达图数据 */
    const masteryRadarData = computed<{ name: string; value: number }[]>(() => {
      return masteryLevels.value.map((m) => ({
        name: m.knowledgePoint,
        value: Math.round(m.mastery * 100)
      }))
    })

    // ═══════════ Actions ═══════════

    /** 获取最新测绘结果 */
    async function fetchLatestCehui(): Promise<void> {
      isLoading.value = true
      error.value = null
      try {
        const result = await cehuiApi.getLatest()
        // 必须无条件赋值：接口返回 null 表示用户已无测绘记录（例如刚被删除），
        // 此时若保留旧值，持久化的陈旧快照会让「学情看板」继续渲染已删除的数据。
        currentCehui.value = result ?? null
      } catch (e) {
        console.warn('[CehuiStore] 获取最新测绘失败:', e)
        error.value = '获取测绘数据失败'
      } finally {
        isLoading.value = false
      }
    }

    /** 根据 ID 获取测绘详情 */
    async function fetchById(id: string): Promise<void> {
      isLoading.value = true
      error.value = null
      try {
        const result = await cehuiApi.getById(id)
        currentCehui.value = result
      } catch (e) {
        console.error('[CehuiStore] 获取测绘详情失败:', e)
        error.value = '获取测绘详情失败'
      } finally {
        isLoading.value = false
      }
    }

    /** 获取测绘历史 */
    async function fetchHistory(page = 1, pageSize = 10): Promise<void> {
      try {
        const result = await cehuiApi.getHistory({ page, pageSize })
        historyList.value = result.list
      } catch (e) {
        console.error('[CehuiStore] 获取测绘历史失败:', e)
      }
    }

    /** 清除测绘数据 */
    function clear(): void {
      currentCehui.value = null
      historyList.value = []
      error.value = null
    }

    return {
      // State
      currentCehui,
      historyList,
      isLoading,
      error,
      // Getters
      hasCehui,
      overallScore,
      masteryLevels,
      cognitiveLoad,
      weakPoints,
      sortedWeakPoints,
      masteryStats,
      masteryRadarData,
      // Actions
      fetchLatestCehui,
      fetchById,
      fetchHistory,
      clear
    }
  },
  {
    persist: {
      key: 'oat_cehui_store',
      storage: localStorage,
      paths: ['currentCehui']
    }
  }
)
