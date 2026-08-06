<script setup lang="ts">
import { useAppStore } from '@/stores/app'
import { storeToRefs } from 'pinia'

const appStore = useAppStore()
const { isLoading } = storeToRefs(appStore)
</script>

<template>
  <div v-if="isLoading" class="global-loading">
    <div class="loading-container">
      <!-- 确定性扫描进度（替代旋转 spinner，仿 Vercel/Linear 加载态） -->
      <div class="loading-mark">
        <svg viewBox="0 0 48 48" class="mark-svg" aria-hidden="true">
          <circle cx="24" cy="24" r="20" fill="none" stroke="rgba(212,163,115,0.12)" stroke-width="1.5" />
          <circle cx="24" cy="24" r="9" fill="none" stroke="rgba(212,163,115,0.25)" stroke-width="1" />
          <circle cx="24" cy="24" r="2.5" fill="#d4a373" />
        </svg>
      </div>
      <div class="loading-bar">
        <div class="loading-bar-fill" />
      </div>
      <div class="loading-meta">
        <span class="loading-id">SYS//DAT-OPS</span>
        <span class="loading-sep">—</span>
        <span class="loading-text">INITIALIZING</span>
        <span class="loading-cursor">_</span>
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
  background: rgba(6, 8, 13, 0.92);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  z-index: 9999;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  width: 240px;
}

/* 精密几何品牌符号（静态，不跳动） */
.loading-mark {
  width: 48px;
  height: 48px;
}

.mark-svg {
  width: 100%;
  height: 100%;
}

/* 确定性扫描进度条 */
.loading-bar {
  position: relative;
  width: 100%;
  height: 2px;
  background: rgba(148, 163, 184, 0.12);
  overflow: hidden;
}

.loading-bar-fill {
  position: absolute;
  inset: 0;
  width: 40%;
  background: linear-gradient(90deg, transparent, #d4a373);
  animation: load-sweep 1.4s var(--ease-in-out-quart, cubic-bezier(0.76, 0, 0.24, 1)) infinite;
}

@keyframes load-sweep {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(350%);
  }
}

/* 等宽状态行（冷酷终端） */
.loading-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 11px;
  letter-spacing: 1.5px;
  color: #94a3b8;
  text-transform: uppercase;
}

.loading-id {
  color: #d4a373;
  font-weight: 600;
}

.loading-sep {
  color: #475569;
}

.loading-text {
  color: #cbd5e1;
}

.loading-cursor {
  color: #d4a373;
  animation: cursor-blink 1s steps(1) infinite;
}

@keyframes cursor-blink {
  0%, 50% {
    opacity: 1;
  }
  50.01%, 100% {
    opacity: 0;
  }
}
</style>
