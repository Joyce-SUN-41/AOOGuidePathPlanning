/**
 * Vitest 全局测试 setup
 * - 为组件测试注册 Ant Design Vue 全量组件（生产环境靠 unplugin-vue-components 按需导入，
 *   测试环境无该插件，需手动全量挂载，否则 a-input / a-form 等组件无法解析）
 * - 补齐 jsdom 缺失的浏览器 API（ResizeObserver / matchMedia），ant-design-vue 内部依赖
 * 该文件仅测试环境加载，不影响生产构建。
 */
import { config } from '@vue/test-utils'
import Antd from 'ant-design-vue'

// 全局注册 Ant Design Vue（所有 mount 自动生效）
config.global.plugins.push(Antd)

// ── 补齐 jsdom 缺失的 API ──
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}
