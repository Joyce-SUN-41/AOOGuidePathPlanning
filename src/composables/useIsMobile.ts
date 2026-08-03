import { ref, onMounted, onUnmounted } from 'vue'

/**
 * 移动端断点判定（主流方案：响应式 matchMedia，SSR/测试环境安全降级）。
 * 默认断点 768px（与 variables.less 的 @mobile 对齐）。
 * 用于动态设置弹窗/抽屉宽度、切换布局，配合 CSS media query 双保险。
 */
export function useIsMobile(breakpoint = 768) {
  const isMobile = ref(false)
  let mql: MediaQueryList | null = null

  const update = () => {
    isMobile.value = mql ? mql.matches : (typeof window !== 'undefined' && window.innerWidth <= breakpoint)
  }

  onMounted(() => {
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      mql = window.matchMedia(`(max-width: ${breakpoint}px)`)
      update()
      // Safari < 14 用 addListener 兼容
      if (mql.addEventListener) {
        mql.addEventListener('change', update)
      } else {
        // @ts-expect-error legacy API
        mql.addListener(update)
      }
    } else {
      update()
    }
  })

  onUnmounted(() => {
    if (mql) {
      if (mql.removeEventListener) {
        mql.removeEventListener('change', update)
      } else {
        // @ts-expect-error legacy API
        mql.removeListener(update)
      }
    }
  })

  return { isMobile }
}
