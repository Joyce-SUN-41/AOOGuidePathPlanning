<script setup lang="ts">
import { RouterView } from 'vue-router'
import GlobalLoading from '@/components/GlobalLoading.vue'

// Ant Design Vue 主题令牌 — 动麦智导 · 深色科技风
const themeConfig = {
  token: {
    // 品牌色 — 动麦金
    colorPrimary: '#D4A373',
    colorInfo: '#4A6CF7',
    colorSuccess: '#34D399',
    colorWarning: '#FBBF24',
    colorError: '#F87171',

    // 文字色（深色主题）
    colorTextBase: '#F8FAFC',
    colorText: '#E2E8F0',
    colorTextSecondary: '#94A3B8',
    colorTextTertiary: '#64748B',

    // 背景 — 深空色系
    colorBgBase: '#0A0D14',
    colorBgContainer: 'rgba(255, 255, 255, 0.04)',
    colorBgElevated: 'rgba(20, 27, 43, 0.92)',
    colorBgLayout: 'transparent',

    // 边框
    colorBorder: 'rgba(255, 255, 255, 0.08)',
    colorBorderSecondary: 'rgba(255, 255, 255, 0.05)',

    // 排版
    fontFamily: `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI',
                  'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei',
                  'Helvetica Neue', Arial, sans-serif`,
    fontSize: 14,
    fontSizeLG: 16,
    fontSizeXL: 20,
    fontSizeHeading1: 36,
    fontSizeHeading2: 28,
    fontSizeHeading3: 22,
    fontSizeHeading4: 18,
    fontSizeHeading5: 15,

    // 圆角
    borderRadius: 8,
    borderRadiusLG: 12,
    borderRadiusSM: 4,
    borderRadiusXS: 2,

    // 间距
    paddingXS: 4,
    paddingSM: 8,
    paddingMD: 16,
    paddingLG: 24,
    paddingXL: 32,

    // 阴影
    boxShadow: '0 1px 3px rgba(0,0,0,0.35), 0 1px 2px rgba(0,0,0,0.25)',
    boxShadowSecondary: '0 4px 12px rgba(0,0,0,0.35), 0 2px 4px rgba(0,0,0,0.25)',

    // 线框
    lineWidth: 1,
    lineType: 'solid',

    // 动画
    motionDurationSlow: '0.3s',
    motionDurationMid: '0.2s',
    motionDurationFast: '0.1s'
  }
}
</script>

<template>
  <a-config-provider :locale="zhCN" :theme="themeConfig">
    <router-view v-slot="{ Component, route }">
      <transition name="page-fade" mode="out-in">
        <component :is="Component" :key="route.path" />
      </transition>
    </router-view>
    <GlobalLoading />
  </a-config-provider>
</template>

<script lang="ts">
import zhCN from 'ant-design-vue/es/locale/zh_CN'

export default {
  data() {
    return {
      zhCN
    }
  }
}
</script>
