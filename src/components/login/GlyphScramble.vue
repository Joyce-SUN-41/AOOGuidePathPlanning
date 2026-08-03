<script setup lang="ts">
/**
 * GlyphScramble —— 字符解码刊头（Kinetic Typography）
 *
 * 每个字符在落位前会快速轮换若干「干扰字符」，随后逐字收敛到正确值。
 * 相比传统的 opacity 淡入，它把「标题出现」表达为一次解码运算，
 * 与 AOO 引擎的叙事一致。
 *
 * 安全与可访问性：
 *   - 外层 span 携带 :aria-label 为最终文本，并对乱码期 DOM 设 aria-hidden，
 *     屏幕阅读器始终只读到终值
 *   - prefers-reduced-motion 时直接渲染终值，不启动任何定时器
 *   - 组件卸载 / 文本变更时清理 rAF，杜绝泄漏
 *   - 仅操作 textContent 派生的响应式数组，不使用 v-html
 */
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 最终文本 */
    text: string
    /** 是否播放解码动画 */
    play?: boolean
    /** 起始延迟 (ms) */
    delay?: number
    /** 每个字符的相对延迟 (ms) */
    stagger?: number
    /** 单字乱码持续时长 (ms) */
    duration?: number
    /** 干扰字符池 */
    pool?: string
  }>(),
  {
    play: true,
    delay: 0,
    stagger: 70,
    duration: 420,
    pool: '野燕麦种传播风水动物优化收敛路径认知图谱'
  }
)

/** 当前每个位置显示的字符 */
const glyphs = ref<string[]>([])
/** 每个位置是否已收敛（用于高亮未定字符） */
const settled = ref<boolean[]>([])

let rafId: number | null = null
let startTs = 0

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

function pickNoise(): string {
  const pool = props.pool || '0123456789'
  const idx = Math.floor(Math.random() * pool.length)
  return pool.charAt(idx) || pool.charAt(0) || '·'
}

function settleAll(): void {
  const chars = Array.from(props.text)
  glyphs.value = chars
  settled.value = chars.map(() => true)
}

function stop(): void {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
}

function tick(ts: number): void {
  const chars = Array.from(props.text)
  if (startTs === 0) startTs = ts
  const elapsed = ts - startTs - props.delay

  let allDone = true
  const nextGlyphs: string[] = []
  const nextSettled: boolean[] = []

  for (let i = 0; i < chars.length; i++) {
    const final = chars[i] ?? ''
    const localStart = i * props.stagger
    const localEnd = localStart + props.duration

    if (elapsed >= localEnd || final === ' ') {
      nextGlyphs.push(final)
      nextSettled.push(true)
    } else if (elapsed < localStart) {
      // 尚未开始：留空占位，避免布局跳动由 min-width 兜底
      nextGlyphs.push('')
      nextSettled.push(false)
      allDone = false
    } else {
      nextGlyphs.push(pickNoise())
      nextSettled.push(false)
      allDone = false
    }
  }

  glyphs.value = nextGlyphs
  settled.value = nextSettled

  if (allDone) {
    stop()
    return
  }
  rafId = requestAnimationFrame(tick)
}

function run(): void {
  stop()
  if (!props.play || prefersReducedMotion() || !props.text) {
    settleAll()
    return
  }
  const chars = Array.from(props.text)
  glyphs.value = chars.map(() => '')
  settled.value = chars.map(() => false)
  startTs = 0
  rafId = requestAnimationFrame(tick)
}

onMounted(run)
onBeforeUnmount(stop)

watch(
  () => [props.text, props.play],
  () => run()
)
</script>

<template>
  <span class="glyph-scramble" :aria-label="text" role="text">
    <span
      v-for="(g, i) in glyphs"
      :key="i"
      class="glyph"
      :class="{ 'is-settled': settled[i] }"
      aria-hidden="true"
      >{{ g || '\u00A0' }}</span
    >
  </span>
</template>

<style scoped>
.glyph-scramble {
  display: inline-flex;
  white-space: pre;
}

.glyph {
  display: inline-block;
  /* 未收敛时用高光色 + 略降不透明度，制造「运算中」的观感 */
  color: rgba(212, 163, 115, 0.62);
  transition: color 90ms linear;
}

.glyph.is-settled {
  color: inherit;
}

@media (prefers-reduced-motion: reduce) {
  .glyph {
    color: inherit;
    transition: none;
  }
}
</style>
