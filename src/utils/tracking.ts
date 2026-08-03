/**
 * 前端埋点上报工具
 *
 * 设计原则:
 * 1. **默认关闭** —— 仅当 VITE_ENABLE_TRACKING === 'true' 时才真正上报，
 *    否则所有 API 变为空操作，不产生任何网络请求，确保零副作用。
 * 2. **永不抛错** —— 埋点失败静默忽略，绝不影响主业务流程。
 * 3. **批量 + 节流** —— 事件先入内存队列，按批次/间隔合并上报，减少请求数。
 * 4. **页面卸载兜底** —— 用 navigator.sendBeacon 在 pagehide 时刷出残留事件。
 *
 * 用法:
 *   import { trackEvent, trackPageView, initTracking } from '@/utils/tracking'
 *   initTracking()                       // main.ts 中调用一次
 *   trackEvent('click_start_diagnose')   // 业务点位
 */

import { getToken } from '@/api'

/** 单条埋点事件 */
export interface TrackEvent {
  event: string
  timestamp: number
  page?: string
  properties?: Record<string, unknown>
}

const ENABLED = import.meta.env.VITE_ENABLE_TRACKING === 'true'
const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const ENDPOINT = `${BASE_URL}/analytics/track`

/** 达到该条数立即上报 */
const FLUSH_SIZE = 10
/** 定时上报间隔 (ms) */
const FLUSH_INTERVAL = 15000
/** 队列上限，防止长时间离线导致内存膨胀 */
const MAX_QUEUE = 100

let queue: TrackEvent[] = []
let timer: ReturnType<typeof setInterval> | null = null
let initialized = false

/** 会话 ID：同一标签页内保持不变 */
const sessionId = (() => {
  try {
    const KEY = 'oat_tracking_sid'
    const existing = sessionStorage.getItem(KEY)
    if (existing) return existing
    const sid = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
    sessionStorage.setItem(KEY, sid)
    return sid
  } catch {
    return `anon-${Date.now().toString(36)}`
  }
})()

function currentPage(): string {
  try {
    return window.location.pathname + window.location.hash
  } catch {
    return ''
  }
}

/** 使用 sendBeacon 上报（页面卸载场景，不可带自定义头） */
function sendByBeacon(events: TrackEvent[]): boolean {
  try {
    if (typeof navigator === 'undefined' || !navigator.sendBeacon) return false
    const blob = new Blob(
      [JSON.stringify({ events, session_id: sessionId })],
      { type: 'application/json' }
    )
    return navigator.sendBeacon(ENDPOINT, blob)
  } catch {
    return false
  }
}

/** 使用 fetch 上报（常规场景，可携带 Token） */
function sendByFetch(events: TrackEvent[]): void {
  try {
    const token = getToken()
    void fetch(ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ events, session_id: sessionId }),
      keepalive: true,
      credentials: 'same-origin',
    }).catch(() => {
      /* 埋点失败静默忽略 */
    })
  } catch {
    /* 埋点失败静默忽略 */
  }
}

/**
 * 立即上报当前队列中的所有事件
 * @param useBeacon 是否强制使用 sendBeacon（页面卸载时传 true）
 */
export function flushEvents(useBeacon = false): void {
  if (!ENABLED || queue.length === 0) return

  const batch = queue
  queue = []

  if (useBeacon) {
    // sendBeacon 失败时回退到 keepalive fetch
    if (!sendByBeacon(batch)) sendByFetch(batch)
    return
  }
  sendByFetch(batch)
}

/** 上报一条自定义事件 */
export function trackEvent(
  event: string,
  properties: Record<string, unknown> = {}
): void {
  if (!ENABLED || !event) return
  try {
    queue.push({
      event,
      timestamp: Date.now(),
      page: currentPage(),
      properties,
    })
    // 超出上限时丢弃最旧的事件
    if (queue.length > MAX_QUEUE) queue = queue.slice(-MAX_QUEUE)
    if (queue.length >= FLUSH_SIZE) flushEvents()
  } catch {
    /* 埋点失败静默忽略 */
  }
}

/** 上报一次页面浏览 */
export function trackPageView(path?: string, title?: string): void {
  trackEvent('page_view', { path: path ?? currentPage(), title: title ?? '' })
}

/** 上报一次错误（可用于全局错误处理器） */
export function trackError(message: string, detail?: Record<string, unknown>): void {
  trackEvent('client_error', { message: String(message).slice(0, 500), ...detail })
}

/**
 * 初始化埋点（在 main.ts 调用一次）
 * 未开启 VITE_ENABLE_TRACKING 时直接返回，不注册任何监听器。
 */
export function initTracking(): void {
  if (!ENABLED || initialized || typeof window === 'undefined') return
  initialized = true

  timer = setInterval(() => flushEvents(), FLUSH_INTERVAL)

  // 页面隐藏/卸载时兜底刷出（pagehide 比 unload 更可靠，且兼容 bfcache）
  window.addEventListener('pagehide', () => flushEvents(true))
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushEvents(true)
  })
}

/** 停止埋点并清理定时器（测试或热更新场景使用） */
export function stopTracking(): void {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  initialized = false
  queue = []
}

/** 埋点是否已启用（供调用方做条件判断） */
export const isTrackingEnabled = ENABLED
