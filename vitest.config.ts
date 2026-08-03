import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    // 测试环境
    environment: 'jsdom',

    // 全局测试 API
    globals: true,

    // 全局测试 setup（注册 Ant Design Vue 等）
    setupFiles: ['./src/test/setup.ts'],

    // 测试文件匹配模式
    include: ['src/**/*.{test,spec}.{ts,tsx,vue}'],

    // 排除文件
    exclude: ['node_modules', 'dist', '.git'],

    // 覆盖率配置
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      reportsDirectory: './coverage',
      include: ['src/**/*.{ts,tsx,vue}'],
      exclude: [
        'src/**/*.d.ts',
        'src/**/*.test.{ts,tsx}',
        'src/**/*.spec.{ts,tsx}',
        'src/types/**',
      ],
      thresholds: {
        statements: 50,
        branches: 40,
        functions: 50,
        lines: 50,
      },
    },

    // 路径别名
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
})
