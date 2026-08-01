<script setup lang="ts">
import { useAppStore } from '@/stores/app'
import { storeToRefs } from 'pinia'

const appStore = useAppStore()
const { isLoading } = storeToRefs(appStore)
</script>

<template>
  <div v-if="isLoading" class="global-loading">
    <div class="loading-container">
      <!-- AOO 流动光条加载动画 — 代替传统 Spin -->
      <div class="aoo-loader">
        <div class="loader-ring">
          <svg viewBox="0 0 120 120" class="loader-svg">
            <defs>
              <linearGradient id="loader-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#D4A373" />
                <stop offset="50%" stop-color="#FAEDCD" />
                <stop offset="100%" stop-color="#D4A373" />
              </linearGradient>
              <filter id="loader-glow">
                <feGaussianBlur stdDeviation="2" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            <!-- 背景轨道 -->
            <circle
              cx="60"
              cy="60"
              r="42"
              fill="none"
              stroke="rgba(255,255,255,0.06)"
              stroke-width="2"
            />
            <!-- 流动光弧 -->
            <circle
              cx="60"
              cy="60"
              r="42"
              fill="none"
              stroke="url(#loader-grad)"
              stroke-width="2"
              stroke-linecap="round"
              stroke-dasharray="60 200"
              filter="url(#loader-glow)"
              class="loader-arc"
            />
            <!-- 中心种子图标 -->
            <g class="loader-seed" transform="translate(60, 60)">
              <circle r="3" fill="rgba(212,163,115,0.5)" />
              <circle r="1.5" fill="#D4A373" />
            </g>
          </svg>
        </div>
        <div class="loader-label">AOO 算法优化中</div>
        <div class="loader-dots">
          <span class="dot" :style="{ animationDelay: '0s' }" />
          <span class="dot" :style="{ animationDelay: '0.2s' }" />
          <span class="dot" :style="{ animationDelay: '0.4s' }" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.global-loading {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 13, 20, 0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 9999;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.aoo-loader {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.loader-ring {
  width: 120px;
  height: 120px;
}

.loader-svg {
  width: 100%;
  height: 100%;
}

/* 流动光弧旋转动画 */
.loader-arc {
  animation: arc-rotate 1.5s linear infinite;
  transform-origin: 60px 60px;
}

@keyframes arc-rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* 中心种子脉冲 */
.loader-seed {
  animation: seed-pulse 2s ease-in-out infinite alternate;
}

@keyframes seed-pulse {
  0% {
    transform: translate(30px, 30px) scale(1);
    opacity: 0.6;
  }
  50% {
    transform: translate(30px, 30px) scale(2.5);
    opacity: 1;
  }
  100% {
    transform: translate(30px, 30px) scale(1);
    opacity: 0.6;
  }
}

.loader-label {
  font-size: 14px;
  font-weight: 500;
  color: #94a3b8;
  letter-spacing: 2px;
}

.loader-dots {
  display: flex;
  gap: 6px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #d4a373;
  animation: dot-sequence 1.2s ease-in-out infinite;
}

@keyframes dot-sequence {
  0%,
  100% {
    opacity: 0.2;
    transform: scale(0.8);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
