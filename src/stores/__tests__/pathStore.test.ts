import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePathStore } from '@/stores/path'
import type { LearningPath } from '@/types'

// ── Mock ant-design-vue message 噪声 ──
vi.mock('ant-design-vue', async () => {
  const actual = await vi.importActual<typeof import('ant-design-vue')>('ant-design-vue')
  return { ...actual, message: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }
})
// 避免轮询/埋点副作用
vi.mock('@/utils/tracking', () => ({ trackEvent: vi.fn() }))
vi.mock('@/api/modules/path', () => ({ pathApi: {} }))

function buildPath(): LearningPath {
  return {
    id: 'p1',
    taskId: 't1',
    diagnosisId: 'd1',
    userId: 'u1',
    createdAt: '2026-01-01T00:00:00Z',
    totalDays: 2,
    totalTasks: 3,
    totalEstimatedHours: 4.5,
    difficultyCurve: [2, 3],
    dailyTasks: [
      [
        {
          id: 'task-1',
          dayIndex: 1,
          orderIndex: 1,
          title: '认识人工智能',
          description: '基础概念',
          knowledgePoint: 'k1_人工智能基础概念',
          estimatedMinutes: 60,
          difficulty: 2,
          resources: [{ type: 'video', title: '导论视频' }],
        },
        {
          id: 'task-2',
          dayIndex: 1,
          orderIndex: 2,
          title: '机器学习入门',
          description: '范式',
          knowledgePoint: 'k2_机器学习基础',
          estimatedMinutes: 90,
          difficulty: 3,
          resources: [{ type: 'article', title: '文章' }],
        },
      ],
      [
        {
          id: 'task-3',
          dayIndex: 2,
          orderIndex: 1,
          title: '深度学习实践',
          description: '动手',
          knowledgePoint: 'k3_深度学习',
          estimatedMinutes: 120,
          difficulty: 4,
          resources: [{ type: 'exercise', title: '练习' }],
        },
      ],
    ],
    metadata: {
      algorithm: 'AOO',
      optimizationScore: 87,
      generationTime: 3.2,
    },
  }
}

describe('pathStore 路径渲染派生数据', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('注入 LearningPath 后 hasPath / taskCount / totalDays 正确', () => {
    const store = usePathStore()
    expect(store.hasPath).toBe(false)
    store.currentPath = buildPath()

    expect(store.hasPath).toBe(true)
    expect(store.taskCount).toBe(3)
    expect(store.totalDays).toBe(2)
    expect(store.estimatedHours).toBe(4.5)
    expect(store.optimizationScore).toBe(87)
  })

  it('dailyTaskViews 按天聚合，标签与每日总时长正确', () => {
    const store = usePathStore()
    store.currentPath = buildPath()
    const views = store.dailyTaskViews

    expect(views.length).toBe(2)
    expect(views[0]!.dayLabel).toBe('第 1 天')
    // 第 1 天：60 + 90 = 150 分钟
    expect(views[0]!.totalMinutes).toBe(150)
    // 第 1 天平均难度：(2+3)/2 = 2.5
    expect(views[0]!.difficulty).toBe(2.5)
    // 第 2 天：120 分钟
    expect(views[1]!.totalMinutes).toBe(120)
    expect(views[1]!.tasks.length).toBe(1)
  })

  it('ganttData 将每日任务转为甘特条目并累加时间偏移', () => {
    const store = usePathStore()
    store.currentPath = buildPath()
    const gantt = store.ganttData

    expect(gantt.length).toBe(3)
    // 第 1 天从 8:00 开始，task-1 占 1h(60min)，间隔 0.25h → task-2 从 9:25
    expect(gantt[0]!.day).toBe(1)
    expect(gantt[0]!.startHour).toBe(8)
    expect(gantt[0]!.durationHours).toBe(1) // 60min
    expect(gantt[1]!.day).toBe(1)
    expect(gantt[1]!.startHour).toBeCloseTo(9.25, 2)
    expect(gantt[2]!.day).toBe(2)
  })

  it('difficultyCurve 直接来源于路径元数据', () => {
    const store = usePathStore()
    store.currentPath = buildPath()
    expect(store.difficultyCurve).toEqual([2, 3])
  })

  it('空路径时不抛错，返回空派生数据', () => {
    const store = usePathStore()
    expect(store.dailyTaskViews).toEqual([])
    expect(store.ganttData).toEqual([])
    expect(store.difficultyCurve).toEqual([])
  })
})
