/**
 * useAuthSequence —— 登录「认证仪式」状态机
 *
 * 把等待从焦虑变成期待：点击登录后不是转一个 spinner，
 * 而是按阶段播放一段可信的系统日志，日志内容严格对应真实发生的事：
 *
 *   1. VERIFYING CREDENTIALS   → 真实的 userStore.login() 请求
 *   2. LOADING COGNITIVE PROFILE → 真实的用户信息落库（login 成功即已返回 userInfo）
 *   3. INITIALIZING AOO ENGINE  → 真实的目标路由预解析 (router.resolve)
 *
 * 设计红线：
 *   - 不伪造任何数据，每一行日志都绑定一个真实步骤的成败
 *   - 任何一步失败即中断，对应行标记 FAILED，不继续往下骗用户
 *   - prefers-reduced-motion 时跳过所有节奏延迟，直接执行并跳转
 *   - 组件卸载后不再写入响应式状态，避免内存泄漏与竞态
 */
import { ref, computed, onBeforeUnmount, readonly } from 'vue'

/** 单行日志的状态 */
export type AuthStepStatus = 'idle' | 'running' | 'ok' | 'failed'

export interface AuthStep {
  /** 等宽日志文案（英文，终端语汇） */
  label: string
  /** 中文可访问描述 */
  description: string
  status: AuthStepStatus
}

/** 整体序列阶段 */
export type AuthPhase = 'idle' | 'collapsing' | 'logging' | 'converging' | 'done' | 'failed'

/** 每一步实际要执行的工作，返回 false 视为失败 */
export type AuthStepRunner = () => Promise<boolean> | boolean

export interface AuthSequenceOptions {
  /** 按钮塌缩耗时 */
  collapseMs?: number
  /** 每行日志之间的最小间隔（保证节奏感，不是假等待） */
  stepGapMs?: number
  /** 粒子收敛 + 白场炸开耗时 */
  convergeMs?: number
}

const DEFAULTS: Required<AuthSequenceOptions> = {
  collapseMs: 260,
  stepGapMs: 180,
  convergeMs: 320
}

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

export function useAuthSequence(options: AuthSequenceOptions = {}) {
  const opts = { ...DEFAULTS, ...options }

  const phase = ref<AuthPhase>('idle')
  const steps = ref<AuthStep[]>([])
  /** 失败提示（用于卡片抖动 + 文案） */
  const errorText = ref('')

  /** 组件是否仍然存活，卸载后阻止一切状态写入 */
  let alive = true
  /** 所有已注册的定时器，卸载时统一清理 */
  const timers = new Set<ReturnType<typeof setTimeout>>()

  onBeforeUnmount(() => {
    alive = false
    timers.forEach((t) => clearTimeout(t))
    timers.clear()
  })

  function wait(ms: number): Promise<void> {
    if (ms <= 0 || prefersReducedMotion()) return Promise.resolve()
    return new Promise((resolve) => {
      const t = setTimeout(() => {
        timers.delete(t)
        resolve()
      }, ms)
      timers.add(t)
    })
  }

  /** 是否处于「运行中」（用于禁用表单） */
  const running = computed(() => phase.value !== 'idle' && phase.value !== 'failed')

  /** 是否应该显示日志面板 */
  const showLog = computed(
    () => phase.value === 'logging' || phase.value === 'converging' || phase.value === 'done'
  )

  /** 是否应该播放白场穿越 */
  const converging = computed(() => phase.value === 'converging' || phase.value === 'done')

  function reset(): void {
    if (!alive) return
    phase.value = 'idle'
    steps.value = []
    errorText.value = ''
  }

  /**
   * 执行认证序列。
   *
   * @param plan 步骤计划，按顺序执行；任一步返回 false 即中断
   * @param onComplete 全部成功后的收尾（通常是 router.push）
   */
  async function run(
    plan: { label: string; description: string; run: AuthStepRunner }[],
    onComplete: () => void | Promise<void>
  ): Promise<boolean> {
    if (!alive || running.value) return false

    errorText.value = ''
    steps.value = plan.map((p) => ({
      label: p.label,
      description: p.description,
      status: 'idle' as AuthStepStatus
    }))

    // ── 阶段 1：按钮塌缩 ──
    phase.value = 'collapsing'
    await wait(opts.collapseMs)
    if (!alive) return false

    // ── 阶段 2：逐行执行 + 输出日志 ──
    phase.value = 'logging'

    for (let i = 0; i < plan.length; i++) {
      if (!alive) return false
      const current = steps.value[i]
      if (current) current.status = 'running'

      let ok = false
      try {
        ok = (await plan[i]!.run()) !== false
      } catch {
        ok = false
      }
      if (!alive) return false

      const after = steps.value[i]
      if (!ok) {
        if (after) after.status = 'failed'
        phase.value = 'failed'
        errorText.value = plan[i]?.description ?? '认证失败'
        return false
      }
      if (after) after.status = 'ok'
      await wait(opts.stepGapMs)
      if (!alive) return false
    }

    // ── 阶段 3：粒子收敛 + 白场炸开 ──
    phase.value = 'converging'
    await wait(opts.convergeMs)
    if (!alive) return false

    phase.value = 'done'
    await onComplete()
    return true
  }

  return {
    phase: readonly(phase),
    steps: readonly(steps),
    errorText: readonly(errorText),
    running,
    showLog,
    converging,
    run,
    reset
  }
}
