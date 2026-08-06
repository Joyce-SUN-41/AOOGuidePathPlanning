/**
 * 学情测绘 · 三个维度自陈量表数据源
 *
 * 维度一「知识层面」: 客观题，由后端知识库提供（共 30 题），前端经 cehuiApi.getQuestions 拉取。
 * 维度二「学习风格层面」: 20 道自陈题（likert 1-5），key 前缀对应四种风格。
 * 维度三「学习准备度层面」: 20 道自陈题（likert 1-5），key 前缀对应动机/元认知/自我效能。
 *
 * 题项 key 的前缀必须与后端聚合逻辑保持一致:
 *   - 学习风格: ambitious_ / sequential_ / steady_ / exploratory_
 *   - 学习准备度: motivation_ / metacognition_ / efficacy_
 */

export interface SelfReportQuestion {
  /** 题项唯一标识（含前缀） */
  key: string
  /** 题面 */
  title: string
  /** 所属聚合桶（用于计算维度得分） */
  bucket: string
  /** 正向题(true) / 反向题(false) —— 反向题在聚合时翻转计分 */
  positive: boolean
}

/* ═════════════════ 维度二: 学习风格 (20 题) ═══════════════ */

export const LEARNING_STYLE_QUESTIONS: SelfReportQuestion[] = [
  // 进取型 ambitious_ (5)
  { key: 'ambitious_1', bucket: 'ambitious', title: '面对有挑战的任务，我会主动要求承担更困难的部分。', positive: true },
  { key: 'ambitious_2', bucket: 'ambitious', title: '我喜欢设定比当前能力略高的目标来逼自己进步。', positive: true },
  { key: 'ambitious_3', bucket: 'ambitious', title: '相比“稳稳拿分”，我更享受“啃下硬骨头”的成就感。', positive: true },
  { key: 'ambitious_4', bucket: 'ambitious', title: '我会在完成基本要求后主动拓展更深入的内容。', positive: true },
  { key: 'ambitious_5', bucket: 'ambitious', title: '别人觉得太难而放弃时，我反而更有动力尝试。', positive: true },

  // 顺序型 sequential_ (5)
  { key: 'sequential_1', bucket: 'sequential', title: '我习惯按步骤、由浅入深地安排学习顺序。', positive: true },
  { key: 'sequential_2', bucket: 'sequential', title: '开始新内容前，我会先理清知识的前后依赖关系。', positive: true },
  { key: 'sequential_3', bucket: 'sequential', title: '我喜欢先掌握基础概念，再进入综合应用。', positive: true },
  { key: 'sequential_4', bucket: 'sequential', title: '有明确路线图（先学什么后学什么）时我更安心。', positive: true },
  { key: 'sequential_5', bucket: 'sequential', title: '我做题时习惯一步步推导，而不是跳着猜答案。', positive: true },

  // 踏实型 steady_ (5)
  { key: 'steady_1', bucket: 'steady', title: '我能长时间专注地重复练习，直到熟练掌握。', positive: true },
  { key: 'steady_2', bucket: 'steady', title: '我偏好按计划稳步推进，不喜欢节奏忽快忽慢。', positive: true },
  { key: 'steady_3', bucket: 'steady', title: '即使进展缓慢，我也能坚持每天完成既定任务。', positive: true },
  { key: 'steady_4', bucket: 'steady', title: '复习巩固旧知识对我而言不枯燥，反而让我踏实。', positive: true },
  { key: 'steady_5', bucket: 'steady', title: '我更在意“学扎实”而不是“学得快”。', positive: true },

  // 探索型 exploratory_ (5)
  { key: 'exploratory_1', bucket: 'exploratory', title: '我喜欢从一个知识点联想到相关的其他领域。', positive: true },
  { key: 'exploratory_2', bucket: 'exploratory', title: '我会主动查阅资料，了解课本之外的延伸知识。', positive: true },
  { key: 'exploratory_3', bucket: 'exploratory', title: '多种解法 / 多种思路的对比能让我兴奋。', positive: true },
  { key: 'exploratory_4', bucket: 'exploratory', title: '我乐于把不同学科的知识串起来理解问题。', positive: true },
  { key: 'exploratory_5', bucket: 'exploratory', title: '遇到开放性问题，我倾向于先发散尝试再收敛。', positive: true },

  // 反向题（negative，聚合时自动翻转计分）— 用于信效度检验（条目5），可识别随意作答
  { key: 'ambitious_r1', bucket: 'ambitious', title: '遇到有挑战的任务，我倾向于绕开或挑更简单的做。', positive: false },
  { key: 'sequential_r1', bucket: 'sequential', title: '学习时我常是想到哪学到哪，没有清晰的先后顺序。', positive: false },
  { key: 'steady_r1', bucket: 'steady', title: '比起反复巩固，我更喜欢快速刷完换新的。', positive: false },
  { key: 'exploratory_r1', bucket: 'exploratory', title: '我通常只盯着一个固定思路，不太愿意尝试别的门路。', positive: false },
]

/* ═════════════════ 维度三: 学习准备度 (20 题) ═══════════════ */

export const LEARNING_READINESS_QUESTIONS: SelfReportQuestion[] = [
  // 学习动机 motivation_ (7)
  { key: 'motivation_1', bucket: 'motivation', title: '我清楚地知道为什么要学习这门课程。', positive: true },
  { key: 'motivation_2', bucket: 'motivation', title: '当学习内容有趣时，我会主动投入更多时间。', positive: true },
  { key: 'motivation_3', bucket: 'motivation', title: '我为自己设定了明确的学习目标。', positive: true },
  { key: 'motivation_4', bucket: 'motivation', title: '即使没有外部督促，我也有内在动力去学。', positive: true },
  { key: 'motivation_5', bucket: 'motivation', title: '取得进步时，我会为自己的成长感到满足。', positive: true },
  { key: 'motivation_6', bucket: 'motivation', title: '我会把“学到的东西”与现实价值联系起来。', positive: true },
  { key: 'motivation_7', bucket: 'motivation', title: '遇到枯燥内容，我也能找到坚持的理由。', positive: true },

  // 元认知 metacognition_ (7)
  { key: 'metacognition_1', bucket: 'metacognition', title: '学习前我会先规划“先学什么、怎么学”。', positive: true },
  { key: 'metacognition_2', bucket: 'metacognition', title: '学习时我会留意自己是否真正理解了。', positive: true },
  { key: 'metacognition_3', bucket: 'metacognition', title: '学完后我会回顾并总结学到的要点。', positive: true },
  { key: 'metacognition_4', bucket: 'metacognition', title: '我发现方法不对时会及时调整策略。', positive: true },
  { key: 'metacognition_5', bucket: 'metacognition', title: '我能判断哪些地方只是“看起来懂了”。', positive: true },
  { key: 'metacognition_6', bucket: 'metacognition', title: '我会根据掌握情况调整复习计划。', positive: true },
  { key: 'metacognition_7', bucket: 'metacognition', title: '我常反思“为什么错”，而不只是改答案。', positive: true },

  // 自我效能 efficacy_ (6)
  { key: 'efficacy_1', bucket: 'efficacy', title: '即使碰到难题，我也相信自己能想办法解决。', positive: true },
  { key: 'efficacy_2', bucket: 'efficacy', title: '我能从容应对有难度的测验。', positive: true },
  { key: 'efficacy_3', bucket: 'efficacy', title: '比起担心失败，我更相信努力会有回报。', positive: true },
  { key: 'efficacy_4', bucket: 'efficacy', title: '面对新知识，我对自己学会它有信心。', positive: true },
  { key: 'efficacy_5', bucket: 'efficacy', title: '遇到挫折时我能较快恢复状态继续学。', positive: true },
  { key: 'efficacy_6', bucket: 'efficacy', title: '我敢于在同学/老师面前表达我的理解或疑问。', positive: true },
]

/* ═════════════════ 聚合工具 ═══════════════ */

export interface StyleItem {
  key: string
  value: number
}

export interface ReadinessItem {
  key: string
  value: number
}

/** 学习准备度画像（第三维自变量，0-1 归一化） */
export interface ReadinessProfile {
  motivation: number
  metacognition: number
  selfEfficacy: number
  rawItems?: ReadinessItem[]
}

/** 将 likert 1-5 按桶聚合为 0-1 归一化得分（反向题自动翻转） */
export function aggregateBuckets(
  items: Record<string, number>,
  questions: SelfReportQuestion[]
): Record<string, number> {
  const sums: Record<string, { total: number; n: number }> = {}
  for (const q of questions) {
    const raw = items[q.key]
    if (raw == null) continue
    const score = q.positive ? raw : 6 - raw // 反向题翻转
    const entry = (sums[q.bucket] ??= { total: 0, n: 0 })
    entry.total += score
    entry.n += 1
  }
  const out: Record<string, number> = {}
  for (const bucket of Object.keys(sums)) {
    const entry = sums[bucket]
    if (!entry) continue
    const { total, n } = entry
    // likert 1-5 → 0-1
    out[bucket] = n > 0 ? Math.min(1, Math.max(0, (total / n - 1) / 4)) : 0
  }
  return out
}

/** 由学习风格自陈作答生成 styleItems（key/value 1-5） */
export function toStyleItems(items: Record<string, number>): StyleItem[] {
  return LEARNING_STYLE_QUESTIONS.filter((q) => items[q.key] != null).map((q) => ({
    key: q.key,
    value: items[q.key] as number
  }))
}

/** 由学习准备度自陈作答生成 ReadinessProfile（motivation/metacognition/self_efficacy 0-1 + rawItems） */
export function toReadinessProfile(items: Record<string, number>): ReadinessProfile {
  const buckets = aggregateBuckets(items, LEARNING_READINESS_QUESTIONS)
  return {
    motivation: round2(buckets['motivation'] ?? 0),
    metacognition: round2(buckets['metacognition'] ?? 0),
    selfEfficacy: round2(buckets['efficacy'] ?? 0),
    rawItems: LEARNING_READINESS_QUESTIONS.filter((q) => items[q.key] != null).map((q) => ({
      key: q.key,
      value: items[q.key] as number
    }))
  }
}

function round2(v: number): number {
  return Math.round(v * 100) / 100
}
