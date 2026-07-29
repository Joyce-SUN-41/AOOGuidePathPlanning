import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 应用全局状态
 */
export const useAppStore = defineStore('app', () => {
  // --- State ---
  /** 侧边栏折叠状态 */
  const collapsed = ref(false)

  /** 全局加载状态 */
  const globalLoading = ref(false)

  /** 菜单主题 */
  const theme = ref<'light' | 'dark'>('dark')

  // --- Getters ---
  const isCollapsed = computed(() => collapsed.value)
  const isLoading = computed(() => globalLoading.value)

  // --- Actions ---
  /** 切换侧边栏折叠 */
  const toggleCollapsed = () => {
    collapsed.value = !collapsed.value
  }

  /** 设置全局加载状态 */
  const setGlobalLoading = (value: boolean) => {
    globalLoading.value = value
  }

  return {
    // State
    collapsed,
    globalLoading,
    theme,
    // Getters
    isCollapsed,
    isLoading,
    // Actions
    toggleCollapsed,
    setGlobalLoading
  }
})
