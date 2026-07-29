import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  DiagnosisResult,
  DiagnosisBrief,
  MasteryItem,
  WeakPoint,
  CognitiveLoadProfile,
} from '@/types'
import { diagnosisApi } from '@/api/modules/diagnosis'

/**
 * 认知诊断状态管理
 *
 * 职责：
 * - 管理当前诊断结果
 * - 提供掌握度、认知负荷、薄弱点等派生数据
 * - 支持历史诊断查询
 */
export const useDiagnosisStore = defineStore(
  'diagnosis',
  () => {
    // ═══════════ State ═══════════

    /** 当前最新诊断结果 */
    const currentDiagnosis = ref<DiagnosisResult | null>(null)

    /** 诊断历史列表 */
    const historyList = ref<DiagnosisBrief[]>([])

    /** 加载状态 */
    const isLoading = ref(false)

    /** 错误信息 */
    const error = ref<string | null>(null)

    // ═══════════ Getters ═══════════

    /** 是否有诊断数据 */
    const hasDiagnosis = computed(() => currentDiagnosis.value !== null)

    /** 综合评分 */
    const overallScore = computed(() => currentDiagnosis.value?.overallScore ?? 0)

    /** 知识点掌握度列表 */
    const masteryLevels = computed<MasteryItem[]>(() => {
      if (!currentDiagnosis.value?.masteryLevels) return []
      return currentDiagnosis.value.masteryLevels
    })

    /** 认知负荷 */
    const cognitiveLoad = computed<CognitiveLoadProfile>(() => {
      return currentDiagnosis.value?.cognitiveLoad ?? {
        memoryLoad: 0,
        attentionLoad: 0,
        processingLoad: 0,
        overall: 0,
      }
    })

    /** 薄弱点列表 */
    const weakPoints = computed<WeakPoint[]>(() => {
      return currentDiagnosis.value?.weakPoints ?? []
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
        weak: levels.filter((m) => m.level === 'weak').length,
      }
    })

    /** 雷达图数据 */
    const masteryRadarData = computed<{ name: string; value: number }[]>(() => {
      return masteryLevels.value.map((m) => ({
        name: m.knowledgePoint,
        value: Math.round(m.mastery * 100),
      }))
    })

    // ═══════════ Actions ═══════════

    /** 获取最新诊断结果 */
    async function fetchLatestDiagnosis(): Promise<void> {
      isLoading.value = true
      error.value = null
      try {
        const result = await diagnosisApi.getLatest()
        if (result) {
          currentDiagnosis.value = result
        }
      } catch (e) {
        console.warn('[DiagnosisStore] 获取最新诊断失败:', e)
        error.value = '获取诊断数据失败'
      } finally {
        isLoading.value = false
      }
    }

    /** 根据 ID 获取诊断详情 */
    async function fetchById(id: string): Promise<void> {
      isLoading.value = true
      error.value = null
      try {
        const result = await diagnosisApi.getById(id)
        currentDiagnosis.value = result
      } catch (e) {
        console.error('[DiagnosisStore] 获取诊断详情失败:', e)
        error.value = '获取诊断详情失败'
      } finally {
        isLoading.value = false
      }
    }

    /** 获取诊断历史 */
    async function fetchHistory(page = 1, pageSize = 10): Promise<void> {
      try {
        const result = await diagnosisApi.getHistory({ page, pageSize })
        historyList.value = result.list
      } catch (e) {
        console.error('[DiagnosisStore] 获取诊断历史失败:', e)
      }
    }

    /** 清除诊断数据 */
    function clear(): void {
      currentDiagnosis.value = null
      historyList.value = []
      error.value = null
    }

    return {
      // State
      currentDiagnosis,
      historyList,
      isLoading,
      error,
      // Getters
      hasDiagnosis,
      overallScore,
      masteryLevels,
      cognitiveLoad,
      weakPoints,
      sortedWeakPoints,
      masteryStats,
      masteryRadarData,
      // Actions
      fetchLatestDiagnosis,
      fetchById,
      fetchHistory,
      clear,
    }
  },
  {
    persist: {
      key: 'oat_diagnosis_store',
      storage: localStorage,
      pick: ['currentDiagnosis'],
    },
  }
)
