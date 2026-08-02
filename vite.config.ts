import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { AntDesignVueResolver } from 'unplugin-vue-components/resolvers'
import { fileURLToPath, URL } from 'node:url'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // 加载环境变量 (VITE_PROXY_TARGET 在 Docker 中指向 backend 容器)
  // process.env 优先（Docker 容器环境变量），其次 .env 文件
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = process.env.VITE_PROXY_TARGET || env.VITE_PROXY_TARGET || 'http://localhost:8000'

  return {
    plugins: [
      vue(),
      Components({
        resolvers: [
          AntDesignVueResolver({
            importStyle: false // css in js
          })
        ]
      })
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
          timeout: 120000,       // LLM 调用可能耗时较长
          proxyTimeout: 120000,  // 后端响应超时 2 分钟
        }
      }
    },
    build: {
      outDir: 'dist',
      assetsDir: 'assets',
      sourcemap: false,
      // 生产构建剔除调试语句（仅 console/debugger；业务提示走 antMessage 不受影响）
      esbuild: {
        drop: ['console', 'debugger'],
      },
      chunkSizeWarningLimit: 1500,
      rollupOptions: {
        output: {
          manualChunks: {
            'ant-design-vue': ['ant-design-vue'],
            'echarts': ['echarts'],
            'vue-vendor': ['vue', 'vue-router', 'pinia']
          }
        }
      }
    }
  }
})
