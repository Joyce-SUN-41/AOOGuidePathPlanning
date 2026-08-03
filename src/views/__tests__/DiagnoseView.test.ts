import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DiagnoseView from '@/views/DiagnoseView.vue'

// ── Mock echarts（DiagnoseView 直接 import * as echarts 并 init 图表）──
vi.mock('echarts', () => ({
  init: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  }),
  graphic: { LinearGradient: class {} },
}))

// ── Mock 诊断 API ──
// vi.mock 工厂会被 hoist，工厂内引用的 mock 必须用 vi.hoisted 声明
const { getQuestionsMock, submitMock } = vi.hoisted(() => ({
  getQuestionsMock: vi.fn(),
  submitMock: vi.fn(),
}))
vi.mock('@/api/modules/diagnosis', () => ({
  diagnosisApi: {
    getQuestions: (...args: unknown[]) => getQuestionsMock(...args),
    submit: (...args: unknown[]) => submitMock(...args),
  },
}))

// ── Mock 路由（DiagnoseView 的 safeNavigate 使用 useRouter）──
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ query: {} }),
}))

// ── Mock ant-design-vue message 噪声 ──
vi.mock('ant-design-vue', async () => {
  const actual = await vi.importActual<typeof import('ant-design-vue')>('ant-design-vue')
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
  }
})

// 生成 >=10 题的题库（满足 loadQuestions 的 length>=10 校验，走真实 API 路径）
const TOPICS = [
  'k1_人工智能基础概念',
  'k2_机器学习基础',
  'k3_深度学习',
  'k4_自然语言处理',
]
function buildQuestions(n = 12) {
  return Array.from({ length: n }, (_, i) => ({
    id: `q${i + 1}`,
    topic: TOPICS[i % TOPICS.length]!,
    difficulty: ((i % 5) + 1) as 1 | 2 | 3 | 4 | 5,
    title: `测试题 ${i + 1}`,
    options: [
      { id: 'a', text: `选项A${i}`, weight: 1 },
      { id: 'b', text: `选项B${i}`, weight: 0 },
    ],
    type: 'single' as const,
  }))
}
const sampleQuestions = buildQuestions()

const sampleResult = {
  id: 'd1',
  userId: 'u1',
  createdAt: '2026-01-01T00:00:00Z',
  subject: '人工智能导论',
  grade: '大学',
  masteryLevels: [],
  cognitiveLoad: { memoryLoad: 0.2, attentionLoad: 0.3, processingLoad: 0.25, overall: 0.25 },
  learningStyle: '视觉型',
  weakPoints: [],
  overallScore: 80,
  summary: '表现良好',
}

describe('DiagnoseView 诊断流程', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    getQuestionsMock.mockReset()
    submitMock.mockReset()
    getQuestionsMock.mockResolvedValue({
      questions: sampleQuestions,
      total: sampleQuestions.length,
      subject: '人工智能导论',
      estimated_duration_min: 10,
    })
    submitMock.mockResolvedValue(sampleResult)
  })

  it('加载时调用 getQuestions 并渲染首题', async () => {
    const wrapper = mount(DiagnoseView, {
      global: { stubs: { CognitiveAuraBackground: true } },
    })
    await flushPromises()

    const vm = wrapper.vm as unknown as { questions: typeof sampleQuestions; pageMode: string }
    expect(getQuestionsMock).toHaveBeenCalled()
    expect(vm.questions.length).toBe(sampleQuestions.length)
    expect(vm.pageMode).toBe('start')
  })

  it('API 失败时回退 Mock 题库（不抛错）', async () => {
    getQuestionsMock.mockRejectedValue(new Error('network error'))
    const wrapper = mount(DiagnoseView, {
      global: { stubs: { CognitiveAuraBackground: true } },
    })
    await flushPromises()
    const vm = wrapper.vm as unknown as { questions: { id: string }[] }
    // 回退题库（MOCK_QUESTIONS）长度 >= 10
    expect(vm.questions.length).toBeGreaterThanOrEqual(10)
  })

  it('构造答案后提交会调用 diagnosisApi.submit 且 payload 正确', async () => {
    const wrapper = mount(DiagnoseView, {
      global: { stubs: { CognitiveAuraBackground: true } },
    })
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      questions: { id: string }[]
      answers: { questionId: string; selectedOption: string; timeSpent: number }[]
      submitAnswers: () => Promise<void>
    }

    // 直接为每题构造一条答案（绕过 UI 翻页交互，聚焦提交链路）
    vm.answers = vm.questions.map((q) => ({
      questionId: q.id,
      selectedOption: 'a',
      timeSpent: 30,
    }))

    await vm.submitAnswers()
    await flushPromises()

    expect(submitMock).toHaveBeenCalledTimes(1)
    const payload = submitMock.mock.calls[0]![0] as { answers: unknown[]; subject: string }
    expect(payload.subject).toBe('人工智能导论')
    expect(Array.isArray(payload.answers)).toBe(true)
    expect(payload.answers.length).toBe(sampleQuestions.length)
  })

  it('提交成功后将结果写入 diagnosisResult', async () => {
    const wrapper = mount(DiagnoseView, {
      global: { stubs: { CognitiveAuraBackground: true } },
    })
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      questions: { id: string }[]
      answers: { questionId: string; selectedOption: string; timeSpent: number }[]
      submitAnswers: () => Promise<void>
      diagnosisResult: typeof sampleResult | null
    }
    vm.answers = vm.questions.map((q) => ({
      questionId: q.id,
      selectedOption: 'a',
      timeSpent: 30,
    }))
    await vm.submitAnswers()
    await flushPromises()

    expect(vm.diagnosisResult).not.toBeNull()
    expect(vm.diagnosisResult?.overallScore).toBe(80)
  })
})
