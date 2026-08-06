/**
 * 轻量全局事件总线
 *
 * 用于跨组件（无父子关系）的即时通知，典型场景：
 *   - 在「我的记录」页删除测绘/路径后，通知 AppLayout 侧边栏刷新「学习统计」
 *   - 测绘完成 / 路径生成后同步刷新统计
 *
 * 相比 Pinia store，这里只做「一次性事件广播」，不持有状态，避免为
 * 单纯的刷新信号引入额外的全局状态。
 */

export type AppEvent =
  /** 测绘记录发生变化（新增 / 删除） */
  | 'cehui:changed'
  /** 学习路径发生变化（新增 / 删除 / 切换方案） */
  | 'path:changed'
  /** 需要刷新侧边栏学习统计 */
  | 'stats:refresh'

type Handler = (payload?: unknown) => void

const listeners = new Map<AppEvent, Set<Handler>>()

/** 订阅事件，返回取消订阅函数 */
export function on(event: AppEvent, handler: Handler): () => void {
  let set = listeners.get(event)
  if (!set) {
    set = new Set()
    listeners.set(event, set)
  }
  set.add(handler)
  return () => off(event, handler)
}

/** 取消订阅 */
export function off(event: AppEvent, handler: Handler): void {
  listeners.get(event)?.delete(handler)
}

/** 发布事件 */
export function emit(event: AppEvent, payload?: unknown): void {
  const set = listeners.get(event)
  if (!set || set.size === 0) return
  // 复制一份，避免处理函数内部取消订阅导致遍历异常
  for (const handler of Array.from(set)) {
    try {
      handler(payload)
    } catch (e) {
      console.error(`[eventBus] "${event}" 处理器执行失败:`, e)
    }
  }
}

export const eventBus = { on, off, emit }
export default eventBus
