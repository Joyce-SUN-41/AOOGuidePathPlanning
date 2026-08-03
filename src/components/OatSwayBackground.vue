<script setup lang="ts">
/**
 * OatSwayBackground —— Hero「麦浪 / 流沙」氛围层（质感版）
 *
 * 设计目标：电影感麦田，而非扁平贴纸粒子。
 *   - 三层景深：后景雾化剪影 → 中景半透明穗 → 前景带高光的麦穗
 *   - 整片麦浪由横向风相位驱动，局部再叠二次抖动
 *   - 流沙用径向柔光 + 短拖尾，避免硬边椭圆
 *   - 底部暖色体积光 + 中央轻 veil，保住标题可读
 */
import { ref, onMounted, onUnmounted, shallowRef } from 'vue'

const props = withDefaults(
  defineProps<{
    density?: number
    opacity?: number
  }>(),
  { density: 90, opacity: 0.88 }
)

const rootRef = ref<HTMLElement | null>(null)
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
let gust = 0 // 阵风包络 0–1

const TARGET_FPS = 30
const FRAME_MS = 1000 / TARGET_FPS

type RGB = readonly [number, number, number]

const C = {
  gold: [212, 163, 115] as RGB,
  goldLite: [232, 198, 150] as RGB,
  cream: [250, 237, 205] as RGB,
  amber: [180, 140, 72] as RGB,
  bronze: [140, 108, 58] as RGB,
  mist: [90, 78, 58] as RGB
}

interface Mote {
  x: number
  y: number
  z: number // 0 远 → 1 近
  vx: number
  vy: number
  size: number
  phase: number
  life: number
  kind: 'dust' | 'husk'
}

interface Culm {
  x: number
  baseOffset: number
  h: number
  phase: number
  lean: number
  layer: 0 | 1 | 2
  kernels: number
  hue: number // 0–1 色相微调
  thickness: number
}

let motes: Mote[] = []
let culms: Culm[] = []
let culmsFar: Culm[] = []
let culmsNear: Culm[] = []

let rngState = 20260803
function rand(): number {
  rngState = (rngState * 16807) % 2147483647
  return (rngState - 1) / 2147483646
}
function randRange(a: number, b: number): number {
  return a + rand() * (b - a)
}

function rgba(c: RGB, a: number): string {
  return `rgba(${c[0]},${c[1]},${c[2]},${Math.max(0, Math.min(1, a))})`
}

function mix(a: RGB, b: RGB, t: number): RGB {
  const u = Math.max(0, Math.min(1, t))
  return [
    a[0] + (b[0] - a[0]) * u,
    a[1] + (b[1] - a[1]) * u,
    a[2] + (b[2] - a[2]) * u
  ] as unknown as RGB
}

/** 横向传播的风场 */
function windAt(x: number, t: number): number {
  const nx = x / Math.max(width, 1)
  return (
    Math.sin(t * 0.65 + nx * 5.2) * 0.55 +
    Math.sin(t * 1.05 + nx * 2.4) * 0.28 +
    Math.sin(t * 0.28 + nx * 9.1) * 0.12 +
    gust * 0.45
  )
}

function makeMote(initial = false): Mote {
  const z = rand()
  const husk = rand() > 0.86
  return {
    x: rand() * width,
    y: initial ? rand() * height : randRange(-20, height * 0.7),
    z,
    vx: randRange(12, 38) * (0.55 + z * 0.7),
    vy: randRange(-3, 5),
    size: husk ? randRange(2.2, 4.2) : randRange(0.9, 2.2) * (0.6 + z),
    phase: rand() * Math.PI * 2,
    life: rand(),
    kind: husk ? 'husk' : 'dust'
  }
}

function rebuildMotes(): void {
  const area = (width * height) / (1280 * 560)
  const n = Math.max(48, Math.round(props.density * Math.min(1.35, Math.max(0.55, area))))
  motes = Array.from({ length: n }, () => makeMote(true))
}

function rebuildCulms(): void {
  culms = []
  const specs: Array<{
    layer: 0 | 1 | 2
    gap: number
    h0: number
    h1: number
  }> = [
    { layer: 0, gap: 14, h0: 0.3, h1: 0.46 },
    { layer: 1, gap: 11, h0: 0.36, h1: 0.54 },
    { layer: 2, gap: 9, h0: 0.42, h1: 0.64 }
  ]

  for (const s of specs) {
    const n = Math.max(22, Math.round(width / s.gap))
    for (let i = 0; i < n; i++) {
      const fx = (i + randRange(0.15, 0.85)) / n
      // 中央略矮，两侧拱起，像包围舞台
      const bowl = 1 - Math.exp(-(((fx - 0.5) * 2.8) ** 2)) * 0.2
      culms.push({
        x: fx * width,
        baseOffset: randRange(-6, 6),
        h: height * randRange(s.h0, s.h1) * bowl,
        phase: rand() * Math.PI * 2,
        lean: randRange(-0.12, 0.12),
        layer: s.layer,
        kernels: s.layer === 0 ? 5 + Math.floor(rand() * 3) : 7 + Math.floor(rand() * 5),
        hue: rand(),
        thickness: 0.9 + s.layer * 0.45 + rand() * 0.35
      })
    }
  }
  culms.sort((a, b) => a.layer - b.layer || a.x - b.x)
  culmsFar = culms.filter((s) => s.layer < 2)
  culmsNear = culms.filter((s) => s.layer === 2)
}

function step(dt: number): void {
  timeSec += dt
  // 阵风：缓慢起伏，偶尔加强
  gust += ((0.35 + 0.65 * Math.sin(timeSec * 0.23) ** 2) - gust) * Math.min(1, dt * 1.8)

  for (const m of motes) {
    const w = windAt(m.x, timeSec)
    const flutter = Math.sin(timeSec * (1.1 + m.z) + m.phase) * (4 + m.z * 5)
    const targetVx = 18 + w * 26 + m.z * 10
    const targetVy = flutter * 0.35 + Math.sin(timeSec * 0.7 + m.phase) * 2 - 1.2
    m.vx += (targetVx - m.vx) * 1.4 * dt
    m.vy += (targetVy - m.vy) * 1.1 * dt
    m.x += m.vx * dt
    m.y += m.vy * dt
    m.life += dt * 0.08

    if (m.x > width + 24) {
      m.x = -16
      m.y = rand() * height * 0.85
    }
    if (m.y > height + 20) m.y = -10
    if (m.y < -24) m.y = height * 0.7
  }
}

function drawAtmosphere(c: CanvasRenderingContext2D): void {
  // 底部体积暖光 —— 麦田自下而上的呼吸感
  const g1 = c.createLinearGradient(0, height * 0.4, 0, height)
  g1.addColorStop(0, 'rgba(0,0,0,0)')
  g1.addColorStop(0.5, rgba(C.gold, 0.07))
  g1.addColorStop(1, rgba(C.amber, 0.18))
  c.fillStyle = g1
  c.fillRect(0, height * 0.4, width, height * 0.6)

  // 左上侧斜向柔光（呼应 hero 燕麦金光晕）
  const g2 = c.createRadialGradient(
    width * 0.28,
    height * 0.08,
    0,
    width * 0.35,
    height * 0.2,
    width * 0.55
  )
  g2.addColorStop(0, rgba(C.cream, 0.07))
  g2.addColorStop(0.45, rgba(C.gold, 0.04))
  g2.addColorStop(1, 'rgba(0,0,0,0)')
  c.fillStyle = g2
  c.fillRect(0, 0, width, height * 0.7)

  // 流沙光带：柔软、低对比、带相位漂移
  for (let i = 0; i < 3; i++) {
    const y = height * (0.58 + i * 0.1) + Math.sin(timeSec * 0.2 + i * 1.4) * 10
    const drift = ((timeSec * 18 + i * 40) % (width * 0.4)) - width * 0.1
    const band = c.createLinearGradient(drift, y, drift + width * 0.75, y - 20)
    const a = 0.045 + 0.025 * Math.sin(timeSec * 0.4 + i)
    band.addColorStop(0, 'rgba(0,0,0,0)')
    band.addColorStop(0.3, rgba(C.goldLite, a))
    band.addColorStop(0.55, rgba(C.cream, a * 0.65))
    band.addColorStop(0.8, rgba(C.gold, a * 0.8))
    band.addColorStop(1, 'rgba(0,0,0,0)')
    c.fillStyle = band
    c.fillRect(0, y - 36, width, 72)
  }
}

function drawMotes(c: CanvasRenderingContext2D): void {
  for (const m of motes) {
    // 文字区略收，但不至于空
    const cx = (m.x / width - 0.5) * 2
    const cy = (m.y / height - 0.38) * 2
    const center = Math.min(1, Math.sqrt(cx * cx * 0.7 + cy * cy))
    const vis = 0.45 + center * 0.55
    const breathe = 0.75 + 0.25 * Math.sin(timeSec * 0.9 + m.phase)
    const a = (0.22 + m.z * 0.45) * vis * breathe
    if (a < 0.03) continue

    const col = m.kind === 'husk' ? mix(C.gold, C.cream, 0.45) : mix(C.gold, C.goldLite, m.z)

    // 柔光核心
    const r = m.size * (1.6 + m.z)
    const glow = c.createRadialGradient(m.x, m.y, 0, m.x, m.y, r * 2.4)
    glow.addColorStop(0, rgba(col, a))
    glow.addColorStop(0.35, rgba(col, a * 0.45))
    glow.addColorStop(1, rgba(col, 0))
    c.fillStyle = glow
    c.beginPath()
    c.arc(m.x, m.y, r * 2.4, 0, Math.PI * 2)
    c.fill()

    // 短拖尾：沿速度方向的柔线
    const spd = Math.hypot(m.vx, m.vy) || 1
    const tx = (m.vx / spd) * (6 + m.z * 10)
    const ty = (m.vy / spd) * (6 + m.z * 10)
    const trail = c.createLinearGradient(m.x - tx, m.y - ty, m.x + tx * 0.2, m.y + ty * 0.2)
    trail.addColorStop(0, rgba(col, 0))
    trail.addColorStop(0.7, rgba(col, a * 0.35))
    trail.addColorStop(1, rgba(col, a * 0.55))
    c.strokeStyle = trail
    c.lineWidth = Math.max(0.6, m.size * 0.55)
    c.lineCap = 'round'
    c.beginPath()
    c.moveTo(m.x - tx, m.y - ty)
    c.lineTo(m.x, m.y)
    c.stroke()

    if (m.kind === 'husk') {
      c.save()
      c.translate(m.x, m.y)
      c.rotate(Math.atan2(m.vy, m.vx) + 0.4)
      c.beginPath()
      c.ellipse(0, 0, m.size * 0.55, m.size * 1.35, 0, 0, Math.PI * 2)
      c.fillStyle = rgba(mix(C.amber, C.cream, 0.3), a * 0.7)
      c.fill()
      c.restore()
    }
  }
}

function stalkColor(layer: 0 | 1 | 2, hue: number, lit: number): RGB {
  const base =
    layer === 0 ? mix(C.mist, C.amber, 0.55) : layer === 1 ? mix(C.amber, C.gold, 0.55) : mix(C.gold, C.cream, 0.35)
  return mix(base, C.goldLite, hue * 0.25 + lit * 0.2)
}

function drawEar(
  c: CanvasRenderingContext2D,
  ax: number,
  ay: number,
  sway: number,
  layer: 0 | 1 | 2,
  kernels: number,
  hue: number,
  alphaMul: number
): void {
  const detail = layer === 0 ? 0.55 : layer === 1 ? 0.8 : 1
  const n = Math.max(4, Math.round(kernels * detail))

  for (let k = 0; k < n; k++) {
    const t = k / Math.max(n - 1, 1)
    // 穗形：上尖下阔的泪滴簇
    const along = t * (18 + layer * 5)
    const spread = Math.sin(t * Math.PI) * (5.5 + layer * 1.8)
    const side = k % 2 === 0 ? -1 : 1
    const ox = side * spread * (0.55 + (1 - t) * 0.45) + sway * 0.08 * t
    const oy = along
    const gx = ax + ox
    const gy = ay + oy
    const tilt = side * (0.35 - t * 0.12) + sway * 0.01

    const lit = 0.35 + 0.65 * Math.max(0, Math.cos(tilt + 0.8)) // 假光照
    const col = stalkColor(layer, hue, lit)
    const shadow = mix(col, C.bronze, 0.45)
    const a = alphaMul * (0.55 + lit * 0.35) * (1 - t * 0.15)

    const rw = (1.5 + layer * 0.35) * (1 - t * 0.25)
    const rh = (3.4 + layer * 0.55) * (1 - t * 0.12)

    c.save()
    c.translate(gx, gy)
    c.rotate(tilt)

    // 阴影半侧
    c.beginPath()
    c.ellipse(0.35, 0.2, rw, rh, 0, 0, Math.PI * 2)
    c.fillStyle = rgba(shadow, a * 0.55)
    c.fill()

    // 主体 + 高光（径向，告别扁平色块）
    const body = c.createRadialGradient(-rw * 0.35, -rh * 0.25, 0, 0, 0, rh)
    body.addColorStop(0, rgba(mix(col, C.cream, 0.55), a))
    body.addColorStop(0.45, rgba(col, a * 0.95))
    body.addColorStop(1, rgba(mix(col, C.bronze, 0.35), a * 0.75))
    c.beginPath()
    c.ellipse(0, 0, rw, rh, 0, 0, Math.PI * 2)
    c.fillStyle = body
    c.fill()

    // 仅前景画软芒，避免线稿感
    if (layer === 2 && t < 0.75) {
      c.beginPath()
      c.moveTo(0, -rh * 0.9)
      c.quadraticCurveTo(side * 0.8, -rh * 1.6, side * 1.6, -rh * 2.3)
      c.strokeStyle = rgba(C.bronze, a * 0.35)
      c.lineWidth = 0.55
      c.lineCap = 'round'
      c.stroke()
    }
    c.restore()
  }
}

function drawCulms(c: CanvasRenderingContext2D, list: Culm[]): void {
  const baseY = height + 4

  for (const s of list) {
    const wind = windAt(s.x, timeSec)
    const local =
      Math.sin(timeSec * 0.72 + s.phase) * (5.5 + s.layer * 1.8) +
      Math.sin(timeSec * 1.35 + s.phase * 1.7) * (2.2 + gust * 2)
    const sway = wind * (10 + s.layer * 3.5) + local
    const bx = s.x + s.baseOffset
    const topX = bx + sway + s.lean * s.h * 0.25
    const topY = baseY - s.h

    // 景深透明度 + 中央轻收
    const cx = Math.abs(s.x / width - 0.5) * 2
    const centerKeep = 0.78 + cx * 0.22
    const layerA = s.layer === 0 ? 0.38 : s.layer === 1 ? 0.62 : 0.9
    const alphaMul = layerA * centerKeep

    const stemCol = stalkColor(s.layer, s.hue, 0.4)

    c.save()
    c.globalAlpha = alphaMul

    // 茎：二次贝塞尔 + 线宽渐隐感（分段描边）
    const midX = bx + sway * 0.4
    const midY = baseY - s.h * 0.52
    if (s.layer === 0) {
      // 后景：更粗更糊，像景深虚化
      c.beginPath()
      c.moveTo(bx, baseY)
      c.quadraticCurveTo(midX, midY, topX, topY)
      c.strokeStyle = rgba(mix(stemCol, C.mist, 0.35), 0.7)
      c.lineWidth = s.thickness + 1.4
      c.lineCap = 'round'
      c.stroke()
    } else {
      c.beginPath()
      c.moveTo(bx, baseY)
      c.quadraticCurveTo(midX, midY, topX, topY)
      const stemGrad = c.createLinearGradient(bx, baseY, topX, topY)
      stemGrad.addColorStop(0, rgba(mix(stemCol, C.bronze, 0.4), 0.35))
      stemGrad.addColorStop(0.55, rgba(stemCol, 0.85))
      stemGrad.addColorStop(1, rgba(mix(stemCol, C.goldLite, 0.3), 0.95))
      c.strokeStyle = stemGrad
      c.lineWidth = s.thickness
      c.lineCap = 'round'
      c.stroke()

      // 茎高光细线
      if (s.layer === 2) {
        c.beginPath()
        c.moveTo(bx - 0.6, baseY)
        c.quadraticCurveTo(midX - 0.5, midY, topX - 0.4, topY)
        c.strokeStyle = rgba(C.cream, 0.18)
        c.lineWidth = Math.max(0.5, s.thickness * 0.28)
        c.stroke()
      }
    }

    drawEar(c, topX, topY, sway, s.layer, s.kernels, s.hue, 1)
    c.restore()
  }
}

function draw(): void {
  if (!ctx) return
  const c = ctx
  c.clearRect(0, 0, width, height)
  drawAtmosphere(c)
  // 远景茎 → 流沙 → 近景茎：粒子穿行在麦浪层次之间
  drawCulms(c, culmsFar)
  drawMotes(c)
  drawCulms(c, culmsNear)
}

function loop(ts: number): void {
  if (!running) {
    rafId.value = null
    return
  }
  const elapsed = ts - lastTs
  if (elapsed >= FRAME_MS) {
    const dt = Math.min(elapsed / 1000, 0.05)
    lastTs = ts - (elapsed % FRAME_MS)
    step(dt)
    draw()
  }
  rafId.value = requestAnimationFrame(loop)
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
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

function resize(): void {
  const canvas = canvasRef.value
  const parent = rootRef.value
  if (!canvas || !parent) return
  const w = parent.clientWidth
  const h = parent.clientHeight
  if (w === 0 || h === 0) return

  dpr = Math.min(window.devicePixelRatio || 1, 2)
  width = w
  height = h
  canvas.width = Math.round(w * dpr)
  canvas.height = Math.round(h * dpr)
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`
  ctx = canvas.getContext('2d', { alpha: true })
  ctx?.setTransform(dpr, 0, 0, dpr, 0, 0)

  rebuildMotes()
  rebuildCulms()
  if (!running) draw()
}

function handleVisibility(): void {
  if (document.hidden) stop()
  else start()
}

onMounted(() => {
  resize()
  if (rootRef.value) {
    resizeObserver = new ResizeObserver(() => resize())
    resizeObserver.observe(rootRef.value)
  }
  document.addEventListener('visibilitychange', handleVisibility)
  start()
})

onUnmounted(() => {
  stop()
  resizeObserver?.disconnect()
  resizeObserver = null
  ctx = null
  motes = []
  culms = []
  document.removeEventListener('visibilitychange', handleVisibility)
})
</script>

<template>
  <div ref="rootRef" class="oat-sway-bg" aria-hidden="true">
    <canvas ref="canvasRef" class="oat-sway-canvas" :style="{ opacity: props.opacity }" />
    <div class="oat-sway-veil" />
    <div class="oat-sway-grain" />
  </div>
</template>

<style scoped>
.oat-sway-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
  border-radius: inherit;
}

.oat-sway-canvas {
  display: block;
  width: 100%;
  height: 100%;
  transition: opacity 0.6s ease;
}

/* 标题区轻压，边缘留给麦浪 */
.oat-sway-veil {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(
      ellipse 46% 40% at 50% 36%,
      rgba(10, 13, 20, 0.42) 0%,
      rgba(10, 13, 20, 0.14) 52%,
      rgba(10, 13, 20, 0) 78%
    ),
    linear-gradient(180deg, rgba(10, 13, 20, 0.12) 0%, transparent 28%, transparent 55%, rgba(10, 13, 20, 0.18) 100%);
}

/* 极轻胶片颗粒，压住数码感 */
.oat-sway-grain {
  position: absolute;
  inset: 0;
  opacity: 0.035;
  mix-blend-mode: soft-light;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size: 180px 180px;
}

@media (prefers-reduced-motion: reduce) {
  .oat-sway-canvas {
    opacity: 0.5 !important;
  }
}
</style>
