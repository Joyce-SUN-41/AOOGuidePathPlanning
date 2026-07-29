import { ref, onMounted, onUnmounted, watch } from 'vue'
import type { Ref } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption, ECharts } from 'echarts'
import { debounce } from '@/utils'

/**
 * ECharts 组合式函数
 * 自动管理图表实例生命周期，响应式更新配置
 */
export function useECharts(containerRef: Ref<HTMLElement | undefined>) {
  const chartInstance = ref<ECharts | null>(null)

  /** 初始化图表 */
  const initChart = () => {
    if (!containerRef.value) return
    chartInstance.value = echarts.init(containerRef.value)
  }

  /** 设置图表配置 */
  const setOption = (option: EChartsOption, notMerge = true) => {
    if (!chartInstance.value) {
      initChart()
    }
    chartInstance.value?.setOption(option, notMerge)
  }

  /** 获取图表实例 */
  const getInstance = () => chartInstance.value

  /** 窗口 resize 处理 */
  const handleResize = debounce(() => {
    chartInstance.value?.resize()
  }, 200)

  onMounted(() => {
    initChart()
    window.addEventListener('resize', handleResize)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    chartInstance.value?.dispose()
    chartInstance.value = null
  })

  return {
    chartInstance,
    setOption,
    getInstance
  }
}
