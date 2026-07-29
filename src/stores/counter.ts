import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 计数器示例 Store
 */
export const useCounterStore = defineStore('counter', () => {
  // --- State ---
  const count = ref(0)

  // --- Getters ---
  const doubleCount = computed(() => count.value * 2)
  const isEven = computed(() => count.value % 2 === 0)

  // --- Actions ---
  const increment = () => {
    count.value++
  }

  const decrement = () => {
    count.value--
  }

  const reset = () => {
    count.value = 0
  }

  const addAmount = (amount: number) => {
    count.value += amount
  }

  return {
    // State
    count,
    // Getters
    doubleCount,
    isEven,
    // Actions
    increment,
    decrement,
    reset,
    addAmount
  }
})
