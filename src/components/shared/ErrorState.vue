<script setup lang="ts">
/**
 * ErrorState — 通用错误状态展示组件
 *
 * 用法:
 *   <ErrorState
 *     title="加载失败"
 *     description="请检查网络连接后重试"
 *     @retry="handleRetry"
 *   />
 */
import { CloseCircleOutlined, ReloadOutlined, HomeOutlined } from '@ant-design/icons-vue'
import { useRouter } from 'vue-router'

withDefaults(
  defineProps<{
    /** 错误标题 */
    title?: string
    /** 错误描述 */
    description?: string
    /** 错误详情（技术信息） */
    detail?: string
    /** 是否显示重试按钮 */
    showRetry?: boolean
    /** 是否显示返回首页按钮 */
    showHome?: boolean
    /** 重试按钮文字 */
    retryText?: string
    /** 是否紧凑模式 */
    compact?: boolean
  }>(),
  {
    title: '加载失败',
    description: '请稍后重试',
    detail: '',
    showRetry: true,
    showHome: false,
    retryText: '重试',
    compact: false
  }
)

const emit = defineEmits<{
  retry: []
}>()

const router = useRouter()

function goHome() {
  router.push('/home')
}
</script>

<template>
  <div class="error-state" :class="{ 'error-state--compact': compact }">
    <div class="error-state__icon">
      <CloseCircleOutlined />
    </div>

    <h3 v-if="title" class="error-state__title">{{ title }}</h3>
    <p v-if="description" class="error-state__desc">{{ description }}</p>

    <div v-if="detail" class="error-state__detail">
      <code>{{ detail }}</code>
    </div>

    <div v-if="showRetry || showHome" class="error-state__actions">
      <a-button v-if="showRetry" type="primary" @click="emit('retry')">
        <ReloadOutlined /> {{ retryText }}
      </a-button>
      <a-button v-if="showHome" @click="goHome"> <HomeOutlined /> 返回首页 </a-button>
    </div>
  </div>
</template>

<style scoped>
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
  min-height: 200px;
}

.error-state--compact {
  padding: 24px 16px;
  min-height: auto;
}

.error-state__icon {
  font-size: 48px;
  color: #ff4d4f;
  margin-bottom: 16px;
  opacity: 0.8;
}

.error-state--compact .error-state__icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.error-state__title {
  font-size: 18px;
  font-weight: 600;
  color: #f8fafc;
  margin: 0 0 8px;
}

.error-state--compact .error-state__title {
  font-size: 15px;
}

.error-state__desc {
  font-size: 14px;
  color: #94a3b8;
  margin: 0 0 16px;
  max-width: 400px;
  line-height: 1.5;
}

.error-state--compact .error-state__desc {
  font-size: 13px;
  margin-bottom: 12px;
}

.error-state__detail {
  margin-bottom: 16px;
  max-width: 600px;
  width: 100%;
}

.error-state__detail code {
  display: block;
  padding: 12px;
  background: rgba(255, 77, 79, 0.08);
  border: 1px solid rgba(255, 77, 79, 0.2);
  border-radius: 8px;
  color: #ff7a7a;
  font-size: 12px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  text-align: left;
  word-break: break-all;
  line-height: 1.5;
}

.error-state__actions {
  display: flex;
  gap: 12px;
  align-items: center;
}
</style>
