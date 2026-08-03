<script setup lang="ts">
/**
 * OatDispersalBackground —— 燕麦种子传播动态背景
 *
 * 视觉隐喻直接来自 AOO（Avena/Oat Optimization）算法的自然启发原型：
 * 燕麦通过三种方式扩散种子，对应算法的三类探索算子。
 *
 *   1. 风传播 (wind)    —— 带冠毛的种子随湍流场大范围漂移 → 全局探索
 *   2. 水传播 (water)   —— 种子沿地表径流下沉、遇涡流打转   → 局部绕行
 *   3. 动物传播 (animal) —— 芒刺附着后沿折线「跳跃式」位移  → Lévy 跳跃
 *
 * 另外叠加两层语义：
 *   - 麦穗剪影随风摆动（场景锚定）
 *   - 种子被「最优解引力点」缓慢吸引并收敛，呼应算法的开发阶段
 *
 * 实现要点（全部为了不掉帧、不打扰阅读）：
 *   - 单个 canvas，devicePixelRatio 上限 2，避免高分屏过度绘制
 *   - 帧率上限 30fps，节流后 CPU 占用极低
 *   - 页面不可见 / prefers-reduced-motion / 组件卸载 时自动停止
 *   - pointer-events: none，绝不拦截交互
 */
import { ref, onMounted, onUnmounted, shallowRef } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 种子总数，会按视口面积自适应缩放 */
    density?: number
    /** 整体不透明度 */
    opacity?: number
    /**
     * 渲染风格。
     * - `ambient`  ：原有柔性风格（圆润种仁 + 柔光引力晕 + lighter 叠加），其它页面沿用
     * - `terminal` ：冷酷终端风格（1px 描边方块 + 虚线拖尾 + 硬边锁定框），登录页使用
     * 默认 `ambient`，保证既有调用方零影响。
     */
    mode?: 'ambient' | 'terminal'
    /**
     * 收敛强度倍率。认证仪式触发时父级可临时放大，
     * 让全部种子被吸向引力点，形成「解收敛」的高潮。
     */
    convergence?: number
    /** 是否绘制中央压暗遮罩（登录页由 BootGrid 统一处理，可关闭） */
    veil?: boolean
  }>(),
  { density: 46, opacity: 0.55, mode: 'ambient', convergence: 1, veil: true }
)

const canvasRef = ref<HTMLCanvasElement | null>(null)
const rafId = shallowRef<number | null>(null)

let ctx: CanvasRenderingContext2D | null = null
let width = 0
let height = 0
let dpr = 1
let resizeObserver: ResizeObserver | null = null
let running = false
let lastTs = 0
let timeSec = 0

const TARGET_FPS = 30
const FRAME_MS = 1000 / TARGET_FPS

// ── 配色：与全站设计系统一致 ──
const COLOR = {
  oatGold: [212, 163, 115] as const, // #D4A373 燕麦金
  auroraBlue: [74, 108, 247] as const, // #4A6CF7 极光蓝
  cyan: [0, 212, 255] as const // #00D4FF 青蓝
}

type Mode = 'wind' | 'water' | 'animal'

interface Seed {
  x: number
  y: number
  vx: number
  vy: number
  mode: Mode
  /** 冠毛半径 */
  r: number
  /** 自转角与角速度 */
  a: number
  va: number
  /** 生命周期 0→1，用于淡入淡出，避免种子突兀出现/消失 */
  life: number
  lifeSpan: number
  /** 噪声相位偏移，保证每颗种子运动独立 */
  seed: number
  /** 动物传播：下一次跳跃倒计时 */
  hopTimer: number
  /** 拖尾点 */
  trail: { x: number; y: number }[]
}

let seeds: Seed[] = []

/** 引力点 —— 象征当前最优解，种子整体向它缓慢收敛 */
const attractor = { x: 0.5, y: 0.55, phase: 0 }

// ─────────────────────────────────────────────
//  确定性伪随机（避免每次刷新差异过大导致观感跳变）
// ─────────────────────────────────────────────
let rngState = 20260801
function rand(): number {
  rngState = (rngState * 16807) % 2147483647
  return (rngState - 1) / 2147483646
}
function randRange(a: number, b: number): number {
  return a + rand() * (b - a)
}

/** 轻量二维值噪声（比 Perlin 便宜，视觉上足够） */
function noise2(x: number, y: number): number {
  const s = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453
  return s - Math.floor(s)
}

/**
 * 湍流风场：位置 + 时间 → 风矢量。
 * 由两组不同频率/相位的正弦叠加而成，产生自然的涡旋感。
 */
function windField(x: number, y: number, t: number): { fx: number; fy: number } {
  const nx = x / Math.max(width, 1)
  const ny = y / Math.max(height, 1)
  const fx =
    Math.sin(ny * 3.1 + t * 0.22) * 0.55 +
    Math.sin(ny * 7.3 - t * 0.13) * 0.22 +
    0.45 // 恒定基础风（自左向右）
  const fy =
    Math.sin(nx * 4.7 - t * 0.19) * 0.32 + Math.cos(nx * 9.1 + t * 0.11) * 0.14 - 0.06
  return { fx, fy }
}

function makeSeed(initial = false): Seed {
  const roll = rand()
  // 风传播占多数，水与动物为点缀 —— 与 AOO 各算子的调用频率相呼应
  const mode: Mode = roll < 0.62 ? 'wind' : roll < 0.84 ? 'water' : 'animal'
  const lifeSpan = randRange(14, 26)
  return {
    x: initial ? randRange(0, width) : randRange(-60, width * 0.12),
    y: mode === 'water' ? randRange(height * 0.55, height) : randRange(0, height),
    vx: randRange(6, 20),
    vy: randRange(-6, 6),
    mode,
    r: mode === 'animal' ? randRange(1.6, 2.6) : randRange(1.8, 3.6),
    a: randRange(0, Math.PI * 2),
    va: randRange(-0.7, 0.7),
    life: initial ? randRange(0.15, 0.9) : 0,
    lifeSpan,
    seed: randRange(0, 1000),
    hopTimer: randRange(0.4, 2.0),
    trail: []
  }
}

function rebuildSeeds(): void {
  // 按视口面积缩放密度，小屏不至于过密
  const area = (width * height) / (1440 * 900)
  const count = Math.round(props.density * Math.min(1.35, Math.max(0.45, area)))
  seeds = Array.from({ length: count }, () => makeSeed(true))
}

// ─────────────────────────────────────────────
//  物理步进
// ─────────────────────────────────────────────
function step(dt: number): void {
  timeSec += dt
  attractor.phase += dt * 0.16
  // 引力点自身缓慢游走，象征最优解在迭代中被不断刷新
  const ax = (0.5 + Math.sin(attractor.phase * 0.7) * 0.17) * width
  const ay = (0.5 + Math.cos(attractor.phase * 0.53) * 0.13) * height

  for (const s of seeds) {
    s.life += dt / s.lifeSpan
    if (s.life >= 1) {
      Object.assign(s, makeSeed(false))
      continue
    }

    if (s.mode === 'wind') {
      // ── 风传播：湍流场驱动 + 冠毛阻尼 ──
      const { fx, fy } = windField(s.x, s.y, timeSec + s.seed)
      s.vx += fx * 26 * dt
      s.vy += fy * 26 * dt
      // 冠毛使种子有明显空气阻力，速度不会无限累积
      s.vx *= 0.975
      s.vy *= 0.975
      // 轻微上浮，模拟冠毛提供的升力
      s.vy -= 3 * dt
      s.va = (noise2(s.seed, timeSec * 0.2) - 0.5) * 1.6
    } else if (s.mode === 'water') {
      // ── 水传播：沿径流向下 + 涡流打转 ──
      const swirl = Math.sin(timeSec * 0.9 + s.seed) * 18
      s.vx += (swirl - s.vx * 0.6) * dt
      s.vy += (14 - s.vy) * dt * 0.9
      s.vx *= 0.99
    } else {
      // ── 动物传播：附着 → 突然跳跃（Lévy 式重尾步长）──
      s.hopTimer -= dt
      if (s.hopTimer <= 0) {
        // 重尾采样：多数小跳，偶尔一次大跳
        const u = Math.max(rand(), 1e-4)
        const magnitude = Math.min(260, 16 / Math.pow(u, 0.7))
        const dir = randRange(0, Math.PI * 2)
        s.vx = Math.cos(dir) * magnitude
        s.vy = Math.sin(dir) * magnitude * 0.6
        s.hopTimer = randRange(0.5, 1.8)
      }
      // 落地摩擦：跳跃后迅速减速，形成「一跳一停」的节奏
      s.vx *= 0.93
      s.vy *= 0.93
    }

    // ── 最优解引力（开发阶段）：越接近生命末期吸引力越强 ──
    // convergence 由父级控制：认证仪式时放大，令种子整体塌缩到引力点
    const gx = ax - s.x
    const gy = ay - s.y
    const gd = Math.hypot(gx, gy) || 1
    const conv = Math.max(1, props.convergence)
    const pull = 5.5 * (conv > 1 ? Math.max(s.life, 0.35) : s.life) * conv
    s.vx += (gx / gd) * pull * dt
    s.vy += (gy / gd) * pull * dt

    s.x += s.vx * dt
    s.y += s.vy * dt
    s.a += s.va * dt

    // 拖尾采样（动物传播的折线跳跃最需要拖尾来体现）
    const trailCap = s.mode === 'animal' ? 8 : 5
    s.trail.push({ x: s.x, y: s.y })
    if (s.trail.length > trailCap) s.trail.shift()

    // 越界回收
    if (s.x < -80 || s.x > width + 80 || s.y < -80 || s.y > height + 80) {
      Object.assign(s, makeSeed(false))
    }
  }
}

// ─────────────────────────────────────────────
//  绘制
// ─────────────────────────────────────────────
function rgba(c: readonly [number, number, number], a: number): string {
  return `rgba(${c[0]},${c[1]},${c[2]},${a})`
}

/** 生命周期淡入淡出包络：两端为 0，中段为 1 */
function envelope(life: number): number {
  return Math.sin(Math.PI * Math.min(1, Math.max(0, life)))
}

function colorOf(mode: Mode): readonly [number, number, number] {
  return mode === 'wind' ? COLOR.oatGold : mode === 'water' ? COLOR.cyan : COLOR.auroraBlue
}

/**
 * terminal 模式的种子绘制：
 * 1px 硬描边方块 + 虚线折线拖尾，无填充柔光、无叠加辉光。
 * 与 ambient 模式完全隔离，互不影响。
 */
function drawSeedTerminal(c: CanvasRenderingContext2D, s: Seed): void {
  const env = envelope(s.life)
  if (env <= 0.01) return
  const col = colorOf(s.mode)

  // ── 虚线折线拖尾 ──
  if (s.trail.length > 1) {
    c.save()
    c.setLineDash([2, 3])
    c.beginPath()
    c.moveTo(s.trail[0]!.x, s.trail[0]!.y)
    for (let i = 1; i < s.trail.length; i++) {
      c.lineTo(s.trail[i]!.x, s.trail[i]!.y)
    }
    c.strokeStyle = rgba(col, 0.16 * env)
    c.lineWidth = 1
    c.lineCap = 'butt'
    c.stroke()
    c.restore()
  }

  // ── 方块本体：描边为主，仅 wind 模式给极小实心点 ──
  const half = Math.max(1.2, s.r * 0.9)
  const px = Math.round(s.x) + 0.5
  const py = Math.round(s.y) + 0.5

  c.beginPath()
  c.rect(px - half, py - half, half * 2, half * 2)
  c.strokeStyle = rgba(col, 0.72 * env)
  c.lineWidth = 1
  c.stroke()

  if (s.mode === 'animal') {
    // 附着型：四角刻度，区分形态
    const tick = half + 2.5
    c.beginPath()
    c.moveTo(px - tick, py)
    c.lineTo(px - half, py)
    c.moveTo(px + half, py)
    c.lineTo(px + tick, py)
    c.strokeStyle = rgba(col, 0.4 * env)
    c.stroke()
  } else if (s.mode === 'wind') {
    c.fillStyle = rgba(col, 0.5 * env)
    c.fillRect(px - 0.5, py - 0.5, 1, 1)
  }
}

/** terminal 模式的引力点：硬边锁定框 + 四角刻度 + 坐标读数 */
function drawAttractorLock(c: CanvasRenderingContext2D): void {
  const ax = (0.5 + Math.sin(attractor.phase * 0.7) * 0.17) * width
  const ay = (0.5 + Math.cos(attractor.phase * 0.53) * 0.13) * height
  const box = 46
  const corner = 11
  const x = Math.round(ax) + 0.5
  const y = Math.round(ay) + 0.5

  c.save()
  c.strokeStyle = rgba(COLOR.oatGold, 0.5)
  c.lineWidth = 1

  // 四角刻度线（不画完整矩形，保留「取景框」语汇）
  const pts: [number, number, number, number][] = [
    [x - box, y - box, corner, 0],
    [x - box, y - box, 0, corner],
    [x + box, y - box, -corner, 0],
    [x + box, y - box, 0, corner],
    [x - box, y + box, corner, 0],
    [x - box, y + box, 0, -corner],
    [x + box, y + box, -corner, 0],
    [x + box, y + box, 0, -corner]
  ]
  c.beginPath()
  for (const [sx, sy, dx, dy] of pts) {
    c.moveTo(sx, sy)
    c.lineTo(sx + dx, sy + dy)
  }
  c.stroke()

  // 中心十字
  c.beginPath()
  c.moveTo(x - 4, y)
  c.lineTo(x + 4, y)
  c.moveTo(x, y - 4)
  c.lineTo(x, y + 4)
  c.strokeStyle = rgba(COLOR.oatGold, 0.75)
  c.stroke()

  // 坐标读数：真实反映引力点的归一化位置
  const nx = (ax / Math.max(width, 1)).toFixed(2)
  const ny = (ay / Math.max(height, 1)).toFixed(2)
  c.font = '10px "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace'
  c.fillStyle = rgba(COLOR.oatGold, 0.55)
  c.textBaseline = 'top'
  c.fillText(`[${nx}, ${ny}]`, x - box, y + box + 6)

  c.restore()
}

function drawSeed(c: CanvasRenderingContext2D, s: Seed): void {
  const env = envelope(s.life)
  if (env <= 0.01) return
  const col = colorOf(s.mode)

  // ── 拖尾 ──
  if (s.trail.length > 1) {
    c.beginPath()
    c.moveTo(s.trail[0]!.x, s.trail[0]!.y)
    for (let i = 1; i < s.trail.length; i++) {
      c.lineTo(s.trail[i]!.x, s.trail[i]!.y)
    }
    c.strokeStyle = rgba(col, 0.1 * env)
    c.lineWidth = s.mode === 'animal' ? 1.1 : 0.8
    c.lineCap = 'round'
    c.stroke()
  }

  c.save()
  c.translate(s.x, s.y)
  c.rotate(s.a)

  if (s.mode === 'wind') {
    // 冠毛（pappus）：一圈放射状细丝 —— 燕麦种子的标志性结构
    const spokes = 7
    c.strokeStyle = rgba(col, 0.34 * env)
    c.lineWidth = 0.7
    for (let i = 0; i < spokes; i++) {
      const ang = (i / spokes) * Math.PI * 2
      c.beginPath()
      c.moveTo(0, 0)
      c.lineTo(Math.cos(ang) * s.r * 3.1, Math.sin(ang) * s.r * 3.1)
      c.stroke()
    }
    // 种仁
    c.beginPath()
    c.ellipse(0, 0, s.r * 0.55, s.r, 0, 0, Math.PI * 2)
    c.fillStyle = rgba(col, 0.78 * env)
    c.fill()
  } else if (s.mode === 'water') {
    // 水面涟漪 + 种仁
    c.beginPath()
    c.arc(0, 0, s.r * 2.6, 0, Math.PI * 2)
    c.strokeStyle = rgba(col, 0.16 * env)
    c.lineWidth = 0.8
    c.stroke()
    c.beginPath()
    c.ellipse(0, 0, s.r * 0.6, s.r * 1.1, 0, 0, Math.PI * 2)
    c.fillStyle = rgba(col, 0.7 * env)
    c.fill()
  } else {
    // 芒刺（awn）：两根带钩的长芒，象征附着动物皮毛
    c.strokeStyle = rgba(col, 0.5 * env)
    c.lineWidth = 0.9
    c.beginPath()
    c.moveTo(0, 0)
    c.lineTo(s.r * 4.2, -s.r * 1.5)
    c.moveTo(0, 0)
    c.lineTo(-s.r * 3.4, -s.r * 2.1)
    c.stroke()
    c.beginPath()
    c.ellipse(0, 0, s.r * 0.7, s.r * 1.25, 0, 0, Math.PI * 2)
    c.fillStyle = rgba(col, 0.82 * env)
    c.fill()
  }

  c.restore()
}

/** 底部麦穗剪影：为整个场景提供「燕麦田」的空间锚点 */
function drawOatSilhouette(c: CanvasRenderingContext2D): void {
  const baseY = height + 6
  const stalks = Math.max(5, Math.round(width / 260))

  for (let i = 0; i <= stalks; i++) {
    // 用确定性函数分布，避免每帧重算随机数
    const fx = (i + 0.5) / (stalks + 1)
    const jitter = noise2(i * 3.7, 11.3)
    const x = fx * width + (jitter - 0.5) * 90
    const h = height * (0.2 + jitter * 0.16)
    const sway = Math.sin(timeSec * 0.45 + i * 1.27) * (6 + jitter * 7)
    const topX = x + sway
    const topY = baseY - h

    c.save()
    c.globalAlpha = 0.3

    // 茎
    c.beginPath()
    c.moveTo(x, baseY)
    c.quadraticCurveTo(x + sway * 0.35, baseY - h * 0.55, topX, topY)
    c.strokeStyle = rgba(COLOR.oatGold, 0.5)
    c.lineWidth = 1.6
    c.lineCap = 'round'
    c.stroke()

    // 小穗：沿茎顶向下交错排列
    const grains = 7
    for (let g = 0; g < grains; g++) {
      const t = g / grains
      const gy = topY + t * h * 0.4
      const spread = (1 - t) * 9 + 3
      const side = g % 2 === 0 ? 1 : -1
      const gx = topX + sway * t * 0.3 + side * spread
      c.beginPath()
      c.ellipse(gx, gy, 2.1, 4.6, side * 0.32, 0, Math.PI * 2)
      c.fillStyle = rgba(COLOR.oatGold, 0.44 - t * 0.16)
      c.fill()
    }
    c.restore()
  }
}

/** 最优解引力点的柔光晕 */
function drawAttractorGlow(c: CanvasRenderingContext2D): void {
  const ax = (0.5 + Math.sin(attractor.phase * 0.7) * 0.17) * width
  const ay = (0.5 + Math.cos(attractor.phase * 0.53) * 0.13) * height
  const pulse = 0.5 + 0.5 * Math.sin(timeSec * 1.1)
  const radius = 110 + pulse * 26

  const grad = c.createRadialGradient(ax, ay, 0, ax, ay, radius)
  grad.addColorStop(0, rgba(COLOR.oatGold, 0.11))
  grad.addColorStop(0.45, rgba(COLOR.auroraBlue, 0.05))
  grad.addColorStop(1, 'rgba(0,0,0,0)')
  c.beginPath()
  c.arc(ax, ay, radius, 0, Math.PI * 2)
  c.fillStyle = grad
  c.fill()
}

function draw(): void {
  if (!ctx) return
  const c = ctx
  c.clearRect(0, 0, width, height)

  if (props.mode === 'terminal') {
    // 冷酷终端风格：不做 lighter 叠加，避免辉光堆积
    c.globalCompositeOperation = 'source-over'
    drawAttractorLock(c)
    for (const s of seeds) drawSeedTerminal(c, s)
    return
  }

  c.globalCompositeOperation = 'lighter'
  drawAttractorGlow(c)
  for (const s of seeds) drawSeed(c, s)
  c.globalCompositeOperation = 'source-over'
  drawOatSilhouette(c)
}

// ─────────────────────────────────────────────
//  主循环
// ─────────────────────────────────────────────
function loop(ts: number): void {
  if (!running) {
    rafId.value = null
    return
  }
  const elapsed = ts - lastTs
  if (elapsed >= FRAME_MS) {
    // dt 限幅：标签页切回时不会因巨大 dt 而「瞬移」
    const dt = Math.min(elapsed / 1000, 0.05)
    lastTs = ts - (elapsed % FRAME_MS)
    step(dt)
    draw()
  }
  rafId.value = requestAnimationFrame(loop)
}

function start(): void {
  if (running || prefersReducedMotion()) return
  running = true
  lastTs = performance.now()
  rafId.value = requestAnimationFrame(loop)
}

function stop(): void {
  running = false
  if (rafId.value !== null) {
    cancelAnimationFrame(rafId.value)
    rafId.value = null
  }
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

function resize(): void {
  const canvas = canvasRef.value
  if (!canvas) return
  const parent = canvas.parentElement
  const w = parent?.clientWidth || window.innerWidth
  const h = parent?.clientHeight || window.innerHeight
  if (w === 0 || h === 0) return

  dpr = Math.min(window.devicePixelRatio || 1, 2)
  width = w
  height = h
  canvas.width = Math.round(w * dpr)
  canvas.height = Math.round(h * dpr)
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`

  ctx = canvas.getContext('2d')
  ctx?.setTransform(dpr, 0, 0, dpr, 0, 0)

  rebuildSeeds()
  // 静态降级时也要画一帧，否则背景全空
  if (!running) draw()
}

function handleVisibility(): void {
  if (document.hidden) stop()
  else start()
}

onMounted(() => {
  resize()
  const canvas = canvasRef.value
  if (canvas?.parentElement) {
    resizeObserver = new ResizeObserver(() => resize())
    resizeObserver.observe(canvas.parentElement)
  }
  document.addEventListener('visibilitychange', handleVisibility)
  start()
})

onUnmounted(() => {
  stop()
  resizeObserver?.disconnect()
  resizeObserver = null
  ctx = null
  seeds = []
  document.removeEventListener('visibilitychange', handleVisibility)
})
</script>

<template>
  <div class="oat-dispersal-bg" aria-hidden="true">
    <canvas ref="canvasRef" class="oat-dispersal-canvas" :style="{ opacity: props.opacity }" />
    <!-- 顶部/底部渐隐遮罩，避免动画干扰正文阅读 -->
    <div v-if="props.veil" class="oat-dispersal-veil" />
  </div>
</template>

<style scoped>
.oat-dispersal-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.oat-dispersal-canvas {
  display: block;
  width: 100%;
  height: 100%;
  transition: opacity 0.6s ease;
}

/* 中央区域压暗，保证卡片文字对比度 */
.oat-dispersal-veil {
  position: absolute;
  inset: 0;
  background: radial-gradient(
    ellipse 62% 55% at 50% 45%,
    rgba(10, 13, 20, 0.62) 0%,
    rgba(10, 13, 20, 0.28) 55%,
    rgba(10, 13, 20, 0) 100%
  );
}

@media (prefers-reduced-motion: reduce) {
  .oat-dispersal-canvas {
    opacity: 0.28 !important;
  }
}
</style>
