<script setup lang="ts">
/**
 * AooFlowField —— 登录页签名背景「活体流场」
 *
 * 为什么重做：
 *   上一版的透视栅格 + 64px 网格，与全站 globals.less 里的 `.grid-bg`
 *   （同为 64px、同色 rgba(148,163,184,0.05)）几乎一模一样，
 *   导致登录页和内页背景「撞脸」，毫无独特性可言。
 *
 * 本组件改用一套只属于登录页的视觉语言 —— 把 AOO 算法本身画出来：
 *
 *   1. 流场 (Flow Field)
 *      用双层 sin/cos 叠加构造一个连续的二维向量场，代表「传播风向」。
 *      场本身随时间缓慢演化，产生有机的呼吸感（解决「干巴」）。
 *
 *   2. 游走粒子 (Walkers)
 *      种子沿流场积分前进，留下细长轨迹。轨迹以极低 alpha 的整屏
 *      淡出叠加实现「拖影」，形成丝绸般的流线织物 —— 这是与
 *      硬栅格截然不同的柔性纹理，却依然冷峻（无彩色光斑、无高斯模糊）。
 *
 *   3. 收敛核 (Attractors)
 *      三个缓慢漂移的最优解候选点。粒子靠近时被吸引并加速，
 *      核周围绘制等值圈 + 十字标记，直观表达「Pareto 三路径」。
 *
 *   4. 等值线脊 (Ridges)
 *      按流场势函数绘制稀疏等高线，给画面加一层地形学质感（层次感）。
 *
 * 性能与安全：
 *   - 单 canvas、单 rAF；DPR 上限 2；帧率上限约 40fps
 *   - 页面不可见 (visibilitychange) 时暂停，节省电量
 *   - 尺寸变化用 ResizeObserver，节流到下一帧
 *   - 卸载时彻底清理 rAF / 监听 / observer
 *   - prefers-reduced-motion 由父级传 animated=false，渲染一帧静态构图
 */
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 是否播放动画；false 时只绘制一帧静态构图 */
    animated?: boolean
    /** 粒子数量基准（会按视口面积自适应） */
    density?: number
    /** 整体不透明度 */
    opacity?: number
    /**
     * 收敛倍率。认证仪式触发时父级放大此值，
     * 所有粒子会被猛烈吸向中心核，形成塌缩高潮。
     */
    convergence?: number
    /** 指针位置（归一化 -1~1），用于流场的局部扰动 */
    pointerX?: number
    pointerY?: number
  }>(),
  {
    animated: true,
    density: 260,
    opacity: 1,
    convergence: 1,
    pointerX: 0,
    pointerY: 0
  }
)

const canvasRef = ref<HTMLCanvasElement | null>(null)

/** 调色：严格单高光色（动麦金）+ 冷灰，禁止彩色光斑 */
const COLOR = {
  gold: [212, 163, 115] as const,
  cyan: [0, 212, 255] as const,
  slate: [148, 163, 184] as const
}

interface Walker {
  x: number
  y: number
  px: number
  py: number
  /** 生命周期 0→1，到 1 后重生，避免轨迹无限堆积 */
  life: number
  span: number
  speed: number
  /** 0 风播 / 1 水播 / 2 动物播 —— 对应 AOO 三种传播模式 */
  kind: 0 | 1 | 2
}

interface Attractor {
  x: number
  y: number
  phase: number
  rate: number
  radius: number
}

let ctx: CanvasRenderingContext2D | null = null
let rafId: number | null = null
let ro: ResizeObserver | null = null

let width = 0
let height = 0
let dpr = 1

let walkers: Walker[] = []
let attractors: Attractor[] = []

let time = 0
let lastTs = 0
/** 帧率上限 ~40fps，够顺滑又省电 */
const FRAME_MS = 25

let paused = false
/** 当前生效的收敛倍率，用插值逼近 props，避免突变 */
let convNow = 1

function rgba(c: readonly [number, number, number], a: number): string {
  return `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`
}

/** 伪随机（无需强随机性，仅用于视觉分布） */
function rand(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

/**
 * 流场：返回给定点的角度。
 * 双层三角函数叠加 + 时间演化 —— 连续、无缝、有机。
 */
function fieldAngle(x: number, y: number, t: number): number {
  const s = 0.0016
  const a =
    Math.sin(x * s + t * 0.18) * 1.7 +
    Math.cos(y * s * 1.25 - t * 0.13) * 1.5 +
    Math.sin((x + y) * s * 0.55 + t * 0.07) * 1.1
  return a
}

/** 势函数，用于绘制等值线脊 */
function potential(x: number, y: number, t: number): number {
  const s = 0.0016
  return (
    Math.cos(x * s + t * 0.18) * 1.7 +
    Math.sin(y * s * 1.25 - t * 0.13) * 1.5
  )
}

function spawnWalker(w?: Walker): Walker {
  const k = Math.random()
  const kind: 0 | 1 | 2 = k < 0.55 ? 0 : k < 0.85 ? 1 : 2
  const x = rand(-40, width + 40)
  const y = rand(-40, height + 40)
  const item = w ?? ({} as Walker)
  item.x = x
  item.y = y
  item.px = x
  item.py = y
  item.life = 0
  item.span = rand(0.0016, 0.0042)
  item.speed = kind === 0 ? rand(0.9, 1.7) : kind === 1 ? rand(0.45, 0.85) : rand(1.5, 2.4)
  item.kind = kind
  return item
}

function buildScene(): void {
  const area = width * height
  // 按面积自适应，并设上下限防止极端视口下过载
  const target = Math.round(
    Math.min(520, Math.max(90, (props.density * area) / (1440 * 900)))
  )
  walkers = new Array(target).fill(null).map(() => spawnWalker())

  attractors = [
    { x: 0, y: 0, phase: 0.0, rate: 0.055, radius: 0.2 },
    { x: 0, y: 0, phase: 2.1, rate: 0.041, radius: 0.28 },
    { x: 0, y: 0, phase: 4.3, rate: 0.033, radius: 0.15 }
  ]
  updateAttractors(0)
}

function updateAttractors(t: number): void {
  for (let i = 0; i < attractors.length; i++) {
    const a = attractors[i]!
    const p = a.phase + t * a.rate
    // 李萨如轨迹，三个核彼此错相，永不重合
    a.x = (0.5 + Math.sin(p) * a.radius) * width
    a.y = (0.5 + Math.cos(p * 1.37) * a.radius * 0.72) * height
  }
}

function resize(): void {
  const cv = canvasRef.value
  if (!cv) return
  const parent = cv.parentElement
  const w = parent?.clientWidth || window.innerWidth
  const h = parent?.clientHeight || window.innerHeight
  dpr = Math.min(2, window.devicePixelRatio || 1)

  width = w
  height = h
  cv.width = Math.max(1, Math.floor(w * dpr))
  cv.height = Math.max(1, Math.floor(h * dpr))
  cv.style.width = `${w}px`
  cv.style.height = `${h}px`

  ctx = cv.getContext('2d')
  if (ctx) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.fillStyle = '#06080d'
    ctx.fillRect(0, 0, width, height)
  }
  buildScene()
}

/** 绘制稀疏等值线脊：给画面加地形学层次 */
function drawRidges(c: CanvasRenderingContext2D, t: number): void {
  const step = 46
  const cols = Math.ceil(width / step)
  const rows = Math.ceil(height / step)

  c.lineWidth = 1
  c.strokeStyle = rgba(COLOR.slate, 0.045)
  c.beginPath()

  for (let j = 0; j <= rows; j++) {
    let started = false
    for (let i = 0; i <= cols; i++) {
      const x = i * step
      const y = j * step
      const p = potential(x, y, t)
      // 只在势函数接近整数等值面时连线，形成断续的等高线
      const near = Math.abs(p - Math.round(p))
      if (near < 0.09) {
        const yy = y + p * 5
        if (!started) {
          c.moveTo(x, yy)
          started = true
        } else {
          c.lineTo(x, yy)
        }
      } else {
        started = false
      }
    }
  }
  c.stroke()
}

/** 收敛核：等值圈 + 十字 + 坐标读数 */
function drawAttractors(c: CanvasRenderingContext2D): void {
  const labels = ['EFFICIENT', 'BALANCED', 'ROBUST']

  for (let i = 0; i < attractors.length; i++) {
    const a = attractors[i]!
    const x = Math.round(a.x) + 0.5
    const y = Math.round(a.y) + 0.5
    const isPrimary = i === 0

    // 等值圈：三层同心，硬描边无光晕
    for (let r = 1; r <= 3; r++) {
      c.beginPath()
      c.arc(x, y, 16 * r, 0, Math.PI * 2)
      c.strokeStyle = rgba(
        isPrimary ? COLOR.gold : COLOR.slate,
        (isPrimary ? 0.16 : 0.09) / r
      )
      c.lineWidth = 1
      c.stroke()
    }

    // 十字标记
    c.beginPath()
    c.moveTo(x - 7, y)
    c.lineTo(x + 7, y)
    c.moveTo(x, y - 7)
    c.lineTo(x, y + 7)
    c.strokeStyle = rgba(isPrimary ? COLOR.gold : COLOR.slate, isPrimary ? 0.55 : 0.28)
    c.lineWidth = 1
    c.stroke()

    // 读数：真实反映归一化坐标，不编造数值
    if (isPrimary) {
      const nx = (a.x / Math.max(width, 1)).toFixed(3)
      const ny = (a.y / Math.max(height, 1)).toFixed(3)
      c.font = '10px "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace'
      c.textBaseline = 'top'
      c.fillStyle = rgba(COLOR.gold, 0.42)
      c.fillText(`${labels[i]}  [${nx}, ${ny}]`, x + 56, y - 5)
    }
  }
}

function stepWalkers(c: CanvasRenderingContext2D, dt: number, t: number): void {
  const conv = convNow
  const pxWorld = (props.pointerX * 0.5 + 0.5) * width
  const pyWorld = (props.pointerY * 0.5 + 0.5) * height

  for (let i = 0; i < walkers.length; i++) {
    const w = walkers[i]!
    w.px = w.x
    w.py = w.y

    const ang = fieldAngle(w.x, w.y, t)
    let vx = Math.cos(ang) * w.speed
    let vy = Math.sin(ang) * w.speed

    // ── 向最近的收敛核偏转：这是 AOO「开发阶段」的可视化 ──
    let best = attractors[0]!
    let bestD = Infinity
    for (let k = 0; k < attractors.length; k++) {
      const a = attractors[k]!
      const d = (a.x - w.x) ** 2 + (a.y - w.y) ** 2
      if (d < bestD) {
        bestD = d
        best = a
      }
    }
    const gd = Math.sqrt(bestD) || 1
    const pull = (conv > 1 ? 0.85 * conv : 0.16) * (w.kind === 2 ? 1.6 : 1)
    vx += ((best.x - w.x) / gd) * pull
    vy += ((best.y - w.y) / gd) * pull

    // ── 指针扰动：鼠标像一根搅动流场的棒 ──
    const dxp = w.x - pxWorld
    const dyp = w.y - pyWorld
    const dp = Math.hypot(dxp, dyp)
    if (dp < 220 && dp > 0.5) {
      const force = (1 - dp / 220) * 1.5
      // 切向推开，形成涡流而非爆散
      vx += (-dyp / dp) * force
      vy += (dxp / dp) * force
    }

    w.x += vx * dt * 60
    w.y += vy * dt * 60
    w.life += w.span * dt * 60

    // 重生：超出边界或寿命到期
    if (w.life >= 1 || w.x < -60 || w.x > width + 60 || w.y < -60 || w.y > height + 60) {
      spawnWalker(w)
      continue
    }

    // 生命包络：两端淡出，中段最亮
    const env = Math.sin(Math.PI * w.life)
    const base =
      w.kind === 0 ? COLOR.slate : w.kind === 1 ? COLOR.cyan : COLOR.gold
    const alpha =
      (w.kind === 0 ? 0.3 : w.kind === 1 ? 0.16 : 0.42) * env * (conv > 1 ? 1.4 : 1)

    c.beginPath()
    c.moveTo(w.px, w.py)
    c.lineTo(w.x, w.y)
    c.strokeStyle = rgba(base, alpha)
    c.lineWidth = w.kind === 2 ? 1.3 : 1
    c.stroke()
  }
}

function frame(ts: number): void {
  rafId = requestAnimationFrame(frame)
  if (paused) return

  const elapsed = ts - lastTs
  if (elapsed < FRAME_MS) return
  const dt = Math.min(0.05, elapsed / 1000)
  lastTs = ts

  const c = ctx
  if (!c) return

  time += dt
  // 收敛倍率平滑逼近目标，避免跳变
  convNow += (props.convergence - convNow) * 0.12

  // ── 拖影：整屏极低 alpha 的暗色覆盖，形成丝绸流线 ──
  c.globalCompositeOperation = 'source-over'
  c.fillStyle = 'rgba(6, 8, 13, 0.085)'
  c.fillRect(0, 0, width, height)

  updateAttractors(time)
  drawRidges(c, time)
  stepWalkers(c, dt, time)
  drawAttractors(c)
}

/** 静态构图：reduced-motion 下只跑若干步积分后定格 */
function renderStatic(): void {
  const c = ctx
  if (!c) return
  c.fillStyle = '#06080d'
  c.fillRect(0, 0, width, height)
  updateAttractors(0)
  drawRidges(c, 0)
  // 预跑 90 步，让流线成型后定格
  for (let n = 0; n < 90; n++) {
    stepWalkers(c, 1 / 60, 0)
  }
  drawAttractors(c)
}

function start(): void {
  stop()
  if (!props.animated) {
    renderStatic()
    return
  }
  lastTs = performance.now()
  rafId = requestAnimationFrame(frame)
}

function stop(): void {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
}

function onVisibility(): void {
  paused = document.hidden
  if (!paused) lastTs = performance.now()
}

onMounted(() => {
  resize()
  start()

  if (typeof ResizeObserver !== 'undefined' && canvasRef.value?.parentElement) {
    ro = new ResizeObserver(() => {
      resize()
      if (!props.animated) renderStatic()
    })
    ro.observe(canvasRef.value.parentElement)
  } else {
    window.addEventListener('resize', resize)
  }

  document.addEventListener('visibilitychange', onVisibility)
})

onBeforeUnmount(() => {
  stop()
  ro?.disconnect()
  ro = null
  window.removeEventListener('resize', resize)
  document.removeEventListener('visibilitychange', onVisibility)
})

watch(
  () => props.animated,
  () => start()
)
</script>

<template>
  <canvas
    ref="canvasRef"
    class="aoo-flow-field"
    :style="{ opacity: props.opacity }"
    aria-hidden="true"
  />
</template>

<style scoped>
.aoo-flow-field {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
</style>
