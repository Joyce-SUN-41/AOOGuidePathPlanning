<script setup lang="ts">
/**
 * SkeletonLoading — 通用骨架屏加载组件
 *
 * 用法:
 *   <SkeletonLoading type="card" :rows="3" />
 *   <SkeletonLoading type="chart" :height="320" />
 */
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 骨架类型 */
    type?: 'card' | 'chart' | 'table' | 'text' | 'form'
    /** 行数（text/table 类型） */
    rows?: number
    /** 高度（chart 类型） */
    height?: number | string
    /** 宽度 */
    width?: number | string
    /** 是否显示动画 */
    animated?: boolean
  }>(),
  {
    type: 'card',
    rows: 3,
    height: 320,
    width: '100%',
    animated: true
  }
)

const style = computed(() => ({
  width: typeof props.width === 'number' ? `${props.width}px` : props.width,
  height: typeof props.height === 'number' ? `${props.height}px` : props.height
}))
</script>

<template>
  <div
    class="skeleton-loading"
    :class="{
      'skeleton-loading--animated': animated,
      [`skeleton-loading--${type}`]: true
    }"
    :style="type === 'chart' ? style : undefined"
  >
    <!-- Card 骨架 -->
    <template v-if="type === 'card'">
      <div class="sk-card-header">
        <div class="sk-line sk-line--title" />
        <div class="sk-line sk-line--sub" />
      </div>
      <div class="sk-card-body">
        <div
          v-for="i in rows"
          :key="i"
          class="sk-line"
          :style="{ width: `${85 - (i - 1) * 10}%` }"
        />
      </div>
    </template>

    <!-- Chart 骨架 -->
    <template v-if="type === 'chart'">
      <div class="sk-chart">
        <div class="sk-chart__bar sk-chart__bar--1" />
        <div class="sk-chart__bar sk-chart__bar--2" />
        <div class="sk-chart__bar sk-chart__bar--3" />
        <div class="sk-chart__bar sk-chart__bar--4" />
        <div class="sk-chart__bar sk-chart__bar--5" />
      </div>
    </template>

    <!-- Table 骨架 -->
    <template v-if="type === 'table'">
      <div class="sk-table-header">
        <div v-for="i in 4" :key="'h' + i" class="sk-cell" />
      </div>
      <div v-for="r in rows" :key="'r' + r" class="sk-table-row">
        <div v-for="i in 4" :key="'c' + i" class="sk-cell" />
      </div>
    </template>

    <!-- Text 骨架 -->
    <template v-if="type === 'text'">
      <div v-for="i in rows" :key="i" class="sk-line" :style="{ width: `${100 - (i - 1) * 8}%` }" />
    </template>

    <!-- Form 骨架 -->
    <template v-if="type === 'form'">
      <div v-for="i in rows" :key="i" class="sk-form-field">
        <div class="sk-line sk-line--label" />
        <div class="sk-line sk-line--input" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.skeleton-loading {
  width: 100%;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  padding: 20px;
  overflow: hidden;
}

/* ---- Shimmer animation ---- */
.skeleton-loading--animated .sk-line,
.skeleton-loading--animated .sk-cell,
.skeleton-loading--animated .sk-chart__bar,
.skeleton-loading--animated .sk-form-field > * {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.04) 25%,
    rgba(255, 255, 255, 0.08) 50%,
    rgba(255, 255, 255, 0.04) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

/* ---- Shared skeletal lines ---- */
.sk-line {
  height: 14px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  margin-bottom: 10px;
}

.sk-line--title {
  width: 40%;
  height: 18px;
}

.sk-line--sub {
  width: 25%;
  height: 12px;
}

.sk-line--label {
  width: 30%;
  height: 12px;
  margin-bottom: 6px;
}

.sk-line--input {
  width: 100%;
  height: 32px;
  margin-bottom: 16px;
}

/* ---- Card ---- */
.sk-card-header {
  margin-bottom: 20px;
}

.sk-card-body {
  margin-top: 4px;
}

/* ---- Chart ---- */
.skeleton-loading--chart {
  position: relative;
  padding: 20px 20px 40px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

.sk-chart {
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  gap: 12px;
  height: 100%;
  min-height: 200px;
  padding-top: 20px;
}

.sk-chart__bar {
  flex: 1;
  border-radius: 6px 6px 0 0;
  background: rgba(255, 255, 255, 0.04);
}

.sk-chart__bar--1 {
  height: 45%;
}
.sk-chart__bar--2 {
  height: 68%;
}
.sk-chart__bar--3 {
  height: 55%;
}
.sk-chart__bar--4 {
  height: 82%;
}
.sk-chart__bar--5 {
  height: 60%;
}

/* ---- Table ---- */
.sk-table-header,
.sk-table-row {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}

.sk-cell {
  flex: 1;
  height: 32px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
}

.sk-table-header .sk-cell {
  height: 36px;
  background: rgba(255, 255, 255, 0.06);
}

/* ---- Form ---- */
.sk-form-field {
  margin-bottom: 4px;
}
</style>
