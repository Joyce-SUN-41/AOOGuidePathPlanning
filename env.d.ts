/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>
  export default component
}

interface ImportMetaEnv {
  readonly VITE_APP_TITLE: string
  readonly VITE_APP_ENV: string
  readonly VITE_API_BASE_URL: string
  readonly VITE_DEBUG: string
  readonly VITE_PROXY_TARGET: string
  /** 'true' 时开启前端埋点上报，其余值（含未定义）均视为关闭 */
  readonly VITE_ENABLE_TRACKING: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
