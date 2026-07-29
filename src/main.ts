import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import router from '@/router'
import App from './App.vue'

// Ant Design Vue 按需加载由 unplugin-vue-components 自动处理
import 'ant-design-vue/dist/reset.css'

// 全局设计系统样式（变量 + 毛玻璃 + 动效 + 组件覆盖 + 工具类）
import '@/assets/styles/globals.less'

const app = createApp(App)

// 状态管理（注册持久化插件）
const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)
app.use(pinia)

// 路由
app.use(router)

// 全局错误处理
app.config.errorHandler = (err, _instance, info) => {
  console.error('Global Error:', err, info)
}

// 挂载应用
app.mount('#app')

// 开发环境输出环境信息
if (import.meta.env.DEV) {
  console.log(`[${import.meta.env.VITE_APP_TITLE}] 当前环境: ${import.meta.env.VITE_APP_ENV}`)
}
