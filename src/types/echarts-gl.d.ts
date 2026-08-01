declare module 'echarts-gl' {
  import type { EChartsExtensionInstallRegisters } from 'echarts'

  /** echarts-gl ECharts 扩展 */
  export function install(registers: EChartsExtensionInstallRegisters): void

  /** Geo3D 组件 */
  export const Geo3DComponent: any
  /** Globe 组件 */
  export const GlobeComponent: any
  /** Map3D 组件 */
  export const Map3DComponent: any
  /** Scatter3D 组件 */
  export const Scatter3DComponent: any
  /** Bar3D 组件 */
  export const Bar3DComponent: any
  /** Surface 组件 */
  export const SurfaceComponent: any
  /** Lines3D 组件 */
  export const Lines3DComponent: any
  /** Line3D 组件 */
  export const Line3DComponent: any

  export default install
}
