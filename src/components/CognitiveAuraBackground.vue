<script setup lang="ts">
/**
 * CognitiveAuraBackground —— 「智能体认知超算场」诊断页动态背景
 *
 * 视觉叙事：一场正在实时推理的多智能体系统——
 *   L0  透视计算地平线（深度感）
 *   L1  活化六边形晶格（底层算力）
 *   L2  流场粒子雾（token / 注意力微尘）
 *   L3  能量光带 + 体积累光
 *   L4  弯曲突触通道 + 光子脉冲
 *   L5  智能体星群 / 枢纽全息环
 *   L6  中央推理核心（多环全息体）
 *   L7  诊断扫描束 + 偶发神经级联闪电
 *
 * 技术点：
 *   - 简易 3D 投影视差 + 指针场扰动（window 监听，canvas 仍 pointer-events:none）
 *   - 值噪声流场驱动粒子
 *   - 边缓存 + 对象池，控制分配
 *   - 帧耗自适应降质（保住 30fps 体感）
 *   - 标签页隐藏 / reduced-motion / 卸载即停
 *
 * 对外接口不变：density / opacity
 */
import { ref, onMounted, onUnmounted, shallowRef } from 'vue'

const props = withDefaults(
  defineProps<{
    density?: number
    opacity?: number
  }>(),
  { density: 36, opacity: 0.9 }
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
let quality = 1 // 1 = full, 0.65 = light（自适应）
let frameBudgetEma = 16

const TARGET_FPS = 30
const FRAME_MS = 1000 / TARGET_FPS

const COLOR = {
  oatGold: [212, 163, 115] as const,
  auroraBlue: [74, 108, 247] as const,
  cyan: [0, 212, 255] as const,
  ice: [180, 220, 255] as const
}

// 指针归一化目标 & 平滑值（用于视差 / 场扰动）
let pointerTx = 0.5
let pointerTy = 0.5
let pointerX = 0.5
let pointerY = 0.5

interface Agent {
  x: number
  y: number
  z: number // 0 近 → 1 远
  vx: number
  vy: number
  phase: number
  rate: number
  r: number
  tint: number
  hub: boolean
  orbit: number // 卫星轨道相位
}

interface Dust {
  x: number
  y: number
  z: number
  life: number
  span: number
  tint: number
  size: number
}

interface Photon {
  a: number
  b: number
  t: number
  speed: number
  tint: number
  arc: number // 弯曲幅度
}

interface Wave {
  x: number
  y: number
  r: number
  maxR: number
  tint: number
  life: number
}

interface Bolt {
  points: { x: number; y: number }[]
  life: number
  tint: number
}

interface HexCell {
  x: number
  y: number
  phase: number
  tint: number
}

let agents: Agent[] = []
let dust: Dust[] = []
let photons: Photon[] = []
let waves: Wave[] = []
let bolts: Bolt[] = []
let hexCells: HexCell[] = []
let edges: { i: number; j: number }[] = []

let edgeAcc = 0
let photonAcc = 0
let waveAcc = 0
let boltAcc = 0
let dustAcc = 0

// 对象池
const photonPool: Photon[] = []
const wavePool: Wave[] = []
const dustPool: Dust[] = []

let rngState = 20260802
function rand(): number {
  rngState = (rngState * 16807) % 2147483647
  return (rngState - 1) / 2147483646
}
function randRange(a: number, b: number): number {
  return a + rand() * (b - a)
}

function rgba(c: readonly [number, number, number], a: number): string {
  return `rgba(${c[0]},${c[1]},${c[2]},${a})`
}
function tintOf(t: number): readonly [number, number, number] {
  return t === 0 ? COLOR.oatGold : t === 1 ? COLOR.auroraBlue : COLOR.cyan
}

/** 廉价值噪声（足够驱动流场） */
function vnoise(x: number, y: number): number {
  const ix = Math.floor(x)
  const iy = Math.floor(y)
  const fx = x - ix
  const fy = y - iy
  const u = fx * fx * (3 - 2 * fx)
  const v = fy * fy * (3 - 2 * fy)
  const h = (i: number, j: number) => {
    const n = Math.sin(i * 127.1 + j * 311.7) * 43758.5453
    return n - Math.floor(n)
  }
  const a = h(ix, iy)
  const b = h(ix + 1, iy)
  const c = h(ix, iy + 1)
  const d = h(ix + 1, iy + 1)
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
}

function flowAngle(x: number, y: number, t: number): number {
  const n = vnoise(x * 0.0018 + t * 0.08, y * 0.0018 - t * 0.06)
  const n2 = vnoise(x * 0.0031 - t * 0.05, y * 0.0031 + t * 0.04)
  return (n * 2 + n2) * Math.PI * 2
}

/** 简易深度投影：把 z 映射为缩放与位移（视差） */
function project(x: number, y: number, z: number): { x: number; y: number; s: number } {
  const parallax = (1 - z) * 28
  const px = x + (pointerX - 0.5) * parallax
  const py = y + (pointerY - 0.5) * parallax * 0.7
  const s = 0.55 + (1 - z) * 0.55
  return { x: px, y: py, s }
}

function acquirePhoton(): Photon {
  return photonPool.pop() || { a: 0, b: 0, t: 0, speed: 1, tint: 0, arc: 0 }
}
function releasePhoton(p: Photon): void {
  if (photonPool.length < 64) photonPool.push(p)
}
function acquireWave(): Wave {
  return wavePool.pop() || { x: 0, y: 0, r: 0, maxR: 0, tint: 0, life: 1 }
}
function releaseWave(w: Wave): void {
  if (wavePool.length < 16) wavePool.push(w)
}
function acquireDust(): Dust {
  return dustPool.pop() || { x: 0, y: 0, z: 0, life: 0, span: 1, tint: 0, size: 1 }
}
function releaseDust(d: Dust): void {
  if (dustPool.length < 120) dustPool.push(d)
}

function spawnDust(): void {
  const d = acquireDust()
  d.x = randRange(0, width)
  d.y = randRange(0, height)
  d.z = randRange(0.15, 0.95)
  d.life = 0
  d.span = randRange(4.5, 10)
  d.tint = Math.floor(rand() * 3)
  d.size = randRange(0.6, 1.8)
  dust.push(d)
}

function rebuild(): void {
  const area = (width * height) / (1440 * 900)
  const scale = Math.min(1.45, Math.max(0.5, area))
  const count = Math.round(props.density * scale)

  agents = Array.from({ length: count }, (_, i) => {
    const hub = i < Math.max(3, Math.round(count * 0.14))
    return {
      x: randRange(width * 0.06, width * 0.94),
      y: randRange(height * 0.08, height * 0.92),
      z: hub ? randRange(0.05, 0.35) : randRange(0.15, 0.9),
      vx: randRange(-6, 6),
      vy: randRange(-6, 6),
      phase: randRange(0, Math.PI * 2),
      rate: randRange(0.7, 1.7),
      r: hub ? randRange(2.8, 4.2) : randRange(1.2, 2.6),
      tint: Math.floor(rand() * 3),
      hub,
      orbit: randRange(0, Math.PI * 2)
    }
  })

  // 六边形激活单元（稀疏采样）
  hexCells = []
  const size = Math.max(36, Math.min(width, height) * 0.048)
  const h = size * Math.sqrt(3)
  let row = 0
  for (let y = h * 0.5; y < height; y += h * 0.85) {
    const off = (row % 2) * size * 1.5
    for (let x = size + off; x < width; x += size * 3) {
      if (rand() > 0.55) {
        hexCells.push({
          x,
          y,
          phase: randRange(0, Math.PI * 2),
          tint: Math.floor(rand() * 3)
        })
      }
    }
    row++
  }

  // 回收旧粒子
  for (const p of photons) releasePhoton(p)
  for (const w of waves) releaseWave(w)
  for (const d of dust) releaseDust(d)
  photons = []
  waves = []
  bolts = []
  dust = []

  const dustTarget = Math.round(55 * scale * quality)
  for (let i = 0; i < dustTarget; i++) spawnDust()

  rebuildEdges()
  edgeAcc = photonAcc = waveAcc = boltAcc = dustAcc = 0
}

function rebuildEdges(): void {
  edges = []
  const linkDist = Math.min(width, height) * 0.26
  for (let i = 0; i < agents.length; i++) {
    const a = agents[i]!
    // 枢纽连更多，远处节点连更少
    let links = 0
    const maxLinks = a.hub ? 5 : 3
    for (let j = i + 1; j < agents.length; j++) {
      const b = agents[j]!
      const d = Math.hypot(a.x - b.x, a.y - b.y)
      const zPenalty = (a.z + b.z) * 40
      if (d < linkDist - zPenalty) {
        edges.push({ i, j })
        links++
        if (links >= maxLinks) break
      }
    }
  }
}

function bezierPoint(
  ax: number,
  ay: number,
  bx: number,
  by: number,
  t: number,
  arc: number
): { x: number; y: number } {
  const mx = (ax + bx) * 0.5
  const my = (ay + by) * 0.5
  const dx = bx - ax
  const dy = by - ay
  const len = Math.hypot(dx, dy) || 1
  const nx = (-dy / len) * arc
  const ny = (dx / len) * arc
  const cx = mx + nx
  const cy = my + ny
  const u = 1 - t
  return {
    x: u * u * ax + 2 * u * t * cx + t * t * bx,
    y: u * u * ay + 2 * u * t * cy + t * t * by
  }
}

function makeBolt(ax: number, ay: number, bx: number, by: number, tint: number): void {
  const pts: { x: number; y: number }[] = []
  const segs = 8
  for (let i = 0; i <= segs; i++) {
    const t = i / segs
    const x = ax + (bx - ax) * t
    const y = ay + (by - ay) * t
    const jitter = (1 - Math.abs(t - 0.5) * 2) * 18
    const ang = Math.atan2(by - ay, bx - ax) + Math.PI / 2
    pts.push({
      x: x + Math.cos(ang) * randRange(-jitter, jitter),
      y: y + Math.sin(ang) * randRange(-jitter, jitter)
    })
  }
  pts[0] = { x: ax, y: ay }
  pts[pts.length - 1] = { x: bx, y: by }
  bolts.push({ points: pts, life: 1, tint })
}

// ─────────────────────────────────────────────
//  步进
// ─────────────────────────────────────────────
function step(dt: number): void {
  timeSec += dt
  // 指针平滑
  pointerX += (pointerTx - pointerX) * Math.min(1, dt * 3.2)
  pointerY += (pointerTy - pointerY) * Math.min(1, dt * 3.2)

  const attractX = pointerX * width
  const attractY = pointerY * height

  for (const n of agents) {
    const damp = n.hub ? 0.45 : 1
    // 流场 + 指针微吸引
    const ang = flowAngle(n.x, n.y, timeSec)
    n.vx += Math.cos(ang) * 10 * dt * damp
    n.vy += Math.sin(ang) * 10 * dt * damp
    const adx = attractX - n.x
    const ady = attractY - n.y
    const ad = Math.hypot(adx, ady) + 1
    n.vx += (adx / ad) * (n.hub ? 2 : 5) * dt
    n.vy += (ady / ad) * (n.hub ? 2 : 5) * dt

    n.x += n.vx * dt * damp
    n.y += n.vy * dt * damp
    n.phase += n.rate * dt
    n.orbit += (0.4 + n.rate * 0.25) * dt

    const sp = Math.hypot(n.vx, n.vy)
    const cap = n.hub ? 7 : 11
    if (sp > cap) {
      n.vx = (n.vx / sp) * cap
      n.vy = (n.vy / sp) * cap
    }
    // 阻尼
    n.vx *= 1 - 0.35 * dt
    n.vy *= 1 - 0.35 * dt

    const m = 28
    if (n.x < m) {
      n.x = m
      n.vx = Math.abs(n.vx)
    } else if (n.x > width - m) {
      n.x = width - m
      n.vx = -Math.abs(n.vx)
    }
    if (n.y < m) {
      n.y = m
      n.vy = Math.abs(n.vy)
    } else if (n.y > height - m) {
      n.y = height - m
      n.vy = -Math.abs(n.vy)
    }
  }

  for (const h of hexCells) h.phase += dt * 0.9

  // 尘埃流场
  dustAcc += dt
  const dustCap = Math.round(70 * quality * Math.min(1.3, (width * height) / (1440 * 900)))
  if (dust.length < dustCap && dustAcc > 0.05) {
    dustAcc = 0
    spawnDust()
  }
  for (let i = dust.length - 1; i >= 0; i--) {
    const d = dust[i]!
    d.life += dt
    const ang = flowAngle(d.x, d.y, timeSec * 1.2)
    const spd = (18 + (1 - d.z) * 22) * dt
    d.x += Math.cos(ang) * spd
    d.y += Math.sin(ang) * spd
    // 指针涡旋
    const dx = d.x - attractX
    const dy = d.y - attractY
    const dist = Math.hypot(dx, dy) + 40
    d.x += (-dy / dist) * 40 * dt
    d.y += (dx / dist) * 40 * dt

    if (d.life > d.span || d.x < -40 || d.x > width + 40 || d.y < -40 || d.y > height + 40) {
      dust.splice(i, 1)
      releaseDust(d)
    }
  }

  edgeAcc += dt
  if (edgeAcc > 0.4) {
    edgeAcc = 0
    rebuildEdges()
  }

  // 光子
  photonAcc += dt
  const maxPhotons = Math.round(22 * quality)
  if (photonAcc > 0.09 && photons.length < maxPhotons && edges.length) {
    photonAcc = 0
    const e = edges[Math.floor(rand() * edges.length)]!
    const forward = rand() > 0.45
    const p = acquirePhoton()
    p.a = forward ? e.i : e.j
    p.b = forward ? e.j : e.i
    p.t = 0
    p.speed = randRange(0.65, 1.35)
    p.tint = agents[p.a]?.tint ?? 0
    p.arc = randRange(-55, 55)
    photons.push(p)
  }
  for (let i = photons.length - 1; i >= 0; i--) {
    const p = photons[i]!
    p.t += p.speed * dt
    if (p.t >= 1) {
      photons.splice(i, 1)
      releasePhoton(p)
    }
  }

  // 扫描波
  waveAcc += dt
  if (waveAcc > 1.4 && waves.length < 3) {
    waveAcc = 0
    const hubs = agents.filter((a) => a.hub)
    if (hubs.length) {
      const h = hubs[Math.floor(rand() * hubs.length)]!
      const w = acquireWave()
      w.x = h.x
      w.y = h.y
      w.r = 6
      w.maxR = Math.min(width, height) * randRange(0.24, 0.42)
      w.tint = h.tint
      w.life = 1
      waves.push(w)
    }
  }
  for (let i = waves.length - 1; i >= 0; i--) {
    const w = waves[i]!
    w.r += w.maxR * 0.58 * dt
    w.life = 1 - w.r / w.maxR
    if (w.life <= 0) {
      waves.splice(i, 1)
      releaseWave(w)
    }
  }

  // 神经级联闪电（枢纽之间）
  boltAcc += dt
  for (let i = bolts.length - 1; i >= 0; i--) {
    bolts[i]!.life -= dt * 2.4
    if (bolts[i]!.life <= 0) bolts.splice(i, 1)
  }
  if (boltAcc > 2.6 && bolts.length < 2 && quality > 0.75) {
    boltAcc = 0
    const hubs = agents.filter((a) => a.hub)
    if (hubs.length >= 2) {
      const a = hubs[Math.floor(rand() * hubs.length)]!
      let b = hubs[Math.floor(rand() * hubs.length)]!
      if (b === a) b = hubs[(hubs.indexOf(a) + 1) % hubs.length]!
      const pa = project(a.x, a.y, a.z)
      const pb = project(b.x, b.y, b.z)
      makeBolt(pa.x, pa.y, pb.x, pb.y, a.tint)
    }
  }
}

// ─────────────────────────────────────────────
//  绘制层
// ─────────────────────────────────────────────
function drawHorizon(c: CanvasRenderingContext2D): void {
  // 深空底 + 透视计算地平线
  const g = c.createLinearGradient(0, height * 0.45, 0, height)
  g.addColorStop(0, 'rgba(0,0,0,0)')
  g.addColorStop(0.35, rgba(COLOR.auroraBlue, 0.035))
  g.addColorStop(1, rgba(COLOR.cyan, 0.055))
  c.fillStyle = g
  c.fillRect(0, height * 0.45, width, height * 0.55)

  const vanishX = width * (0.5 + (pointerX - 0.5) * 0.08)
  const vanishY = height * 0.52
  const lines = Math.round(14 * quality)
  c.lineWidth = 0.7
  for (let i = 0; i <= lines; i++) {
    const t = i / lines
    const x = width * t
    const alpha = 0.035 + Math.sin(t * Math.PI) * 0.025
    c.strokeStyle = rgba(COLOR.auroraBlue, alpha)
    c.beginPath()
    c.moveTo(x, height)
    c.lineTo(vanishX, vanishY)
    c.stroke()
  }
  // 水平纵深线
  for (let i = 1; i <= 7; i++) {
    const p = i / 8
    const y = vanishY + (height - vanishY) * Math.pow(p, 1.6)
    const spread = (y - vanishY) / (height - vanishY)
    const half = width * 0.5 * spread
    c.strokeStyle = rgba(COLOR.cyan, 0.03 + (1 - spread) * 0.04)
    c.beginPath()
    c.moveTo(vanishX - half, y)
    c.lineTo(vanishX + half, y)
    c.stroke()
  }
}

function drawHexLattice(c: CanvasRenderingContext2D): void {
  const size = Math.max(36, Math.min(width, height) * 0.048)
  const breath = 0.5 + 0.5 * Math.sin(timeSec * 0.32)
  c.strokeStyle = rgba(COLOR.auroraBlue, 0.025 + breath * 0.02)
  c.lineWidth = 0.65
  c.beginPath()
  let row = 0
  const h = size * Math.sqrt(3)
  const stepY = quality < 0.8 ? h * 1.1 : h * 0.85
  for (let y = -h; y < height + h; y += stepY) {
    const offset = (row % 2) * size * 1.5
    for (let x = -size * 2 + offset; x < width + size * 2; x += size * 3) {
      for (let k = 0; k < 6; k++) {
        const a0 = (Math.PI / 3) * k - Math.PI / 6
        const x0 = x + Math.cos(a0) * size
        const y0 = y + Math.sin(a0) * size
        if (k === 0) c.moveTo(x0, y0)
        else c.lineTo(x0, y0)
      }
      c.closePath()
    }
    row++
  }
  c.stroke()

  // 活化单元脉冲
  for (const cell of hexCells) {
    const pulse = 0.5 + 0.5 * Math.sin(cell.phase + timeSec * 1.4)
    if (pulse < 0.55) continue
    const col = tintOf(cell.tint)
    const a = (pulse - 0.55) * 0.22
    c.strokeStyle = rgba(col, a)
    c.lineWidth = 1.1
    c.beginPath()
    for (let k = 0; k < 6; k++) {
      const ang = (Math.PI / 3) * k - Math.PI / 6
      const x0 = cell.x + Math.cos(ang) * size * 0.72
      const y0 = cell.y + Math.sin(ang) * size * 0.72
      if (k === 0) c.moveTo(x0, y0)
      else c.lineTo(x0, y0)
    }
    c.closePath()
    c.stroke()
    c.fillStyle = rgba(col, a * 0.35)
    c.fill()
  }
}

function drawVolumetricOrbs(c: CanvasRenderingContext2D): void {
  const orbs = [
    { nx: 0.22 + Math.sin(timeSec * 0.11) * 0.04, ny: 0.3, r: 0.42, tint: 1 },
    { nx: 0.78 + Math.cos(timeSec * 0.09) * 0.04, ny: 0.35, r: 0.38, tint: 2 },
    { nx: 0.5 + Math.sin(timeSec * 0.07) * 0.03, ny: 0.7, r: 0.45, tint: 0 },
    { nx: 0.35, ny: 0.55 + Math.cos(timeSec * 0.13) * 0.04, r: 0.3, tint: 2 }
  ]
  for (const o of orbs) {
    const cx = o.nx * width + (pointerX - 0.5) * 20
    const cy = o.ny * height + (pointerY - 0.5) * 14
    const r = o.r * Math.min(width, height)
    const col = tintOf(o.tint)
    const g = c.createRadialGradient(cx, cy, 0, cx, cy, r)
    g.addColorStop(0, rgba(col, 0.14))
    g.addColorStop(0.4, rgba(col, 0.05))
    g.addColorStop(1, 'rgba(0,0,0,0)')
    c.fillStyle = g
    c.beginPath()
    c.arc(cx, cy, r, 0, Math.PI * 2)
    c.fill()
  }
}

function drawEnergyBands(c: CanvasRenderingContext2D): void {
  const bands = [
    { y: 0.26, amp: 0.04, speed: 0.2, col: COLOR.auroraBlue, alpha: 0.075 },
    { y: 0.52, amp: 0.05, speed: -0.15, col: COLOR.cyan, alpha: 0.065 },
    { y: 0.74, amp: 0.035, speed: 0.24, col: COLOR.oatGold, alpha: 0.055 }
  ]
  const stepX = quality < 0.8 ? 32 : 20
  for (const b of bands) {
    const baseY = b.y * height
    const grad = c.createLinearGradient(0, baseY - height * 0.1, 0, baseY + height * 0.1)
    grad.addColorStop(0, 'rgba(0,0,0,0)')
    grad.addColorStop(0.5, rgba(b.col, b.alpha))
    grad.addColorStop(1, 'rgba(0,0,0,0)')
    c.fillStyle = grad
    c.beginPath()
    c.moveTo(0, baseY)
    for (let x = 0; x <= width; x += stepX) {
      const y =
        baseY +
        Math.sin(x * 0.005 + timeSec * b.speed) * height * b.amp +
        Math.sin(x * 0.013 + timeSec * b.speed * 1.8) * height * b.amp * 0.4
      c.lineTo(x, y)
    }
    for (let x = width; x >= 0; x -= stepX) {
      const y = baseY + Math.sin(x * 0.005 + timeSec * b.speed) * height * b.amp + height * 0.085
      c.lineTo(x, y)
    }
    c.closePath()
    c.fill()
  }
}

function drawDust(c: CanvasRenderingContext2D): void {
  for (const d of dust) {
    const p = project(d.x, d.y, d.z)
    const fade = Math.sin((d.life / d.span) * Math.PI)
    const col = tintOf(d.tint)
    const r = d.size * p.s
    c.fillStyle = rgba(col, 0.22 * fade * (1.1 - d.z))
    c.beginPath()
    c.arc(p.x, p.y, r, 0, Math.PI * 2)
    c.fill()
  }
}

function drawLinks(c: CanvasRenderingContext2D): void {
  const maxD = Math.min(width, height) * 0.28
  for (const e of edges) {
    const a = agents[e.i]!
    const b = agents[e.j]!
    const pa = project(a.x, a.y, a.z)
    const pb = project(b.x, b.y, b.z)
    const d = Math.hypot(pa.x - pb.x, pa.y - pb.y)
    if (d > maxD) continue
    const t = 1 - d / maxD
    const col = tintOf(Math.min(a.tint, b.tint))
    const hubBoost = a.hub || b.hub ? 1.4 : 1
    const arc = Math.sin((a.phase + b.phase) * 0.5 + timeSec * 0.3) * (36 + d * 0.04)

    const mx = (pa.x + pb.x) * 0.5
    const my = (pa.y + pb.y) * 0.5
    const dx = pb.x - pa.x
    const dy = pb.y - pa.y
    const len = Math.hypot(dx, dy) || 1
    const cx = mx + (-dy / len) * arc * 0.35
    const cy = my + (dx / len) * arc * 0.35

    c.strokeStyle = rgba(col, 0.13 * t * t * hubBoost)
    c.lineWidth = (a.hub || b.hub ? 1.2 : 0.75) * ((pa.s + pb.s) * 0.55)
    c.beginPath()
    c.moveTo(pa.x, pa.y)
    c.quadraticCurveTo(cx, cy, pb.x, pb.y)
    c.stroke()
  }
}

function drawPhotons(c: CanvasRenderingContext2D): void {
  for (const p of photons) {
    const a = agents[p.a]
    const b = agents[p.b]
    if (!a || !b) continue
    const pa = project(a.x, a.y, a.z)
    const pb = project(b.x, b.y, b.z)
    const ease = p.t * p.t * (3 - 2 * p.t)
    const cur = bezierPoint(pa.x, pa.y, pb.x, pb.y, ease, p.arc)
    const prev = bezierPoint(pa.x, pa.y, pb.x, pb.y, Math.max(0, ease - 0.07), p.arc)
    const fade = Math.sin(p.t * Math.PI)
    const col = tintOf(p.tint)

    c.strokeStyle = rgba(col, 0.45 * fade)
    c.lineWidth = 2
    c.beginPath()
    c.moveTo(prev.x, prev.y)
    c.lineTo(cur.x, cur.y)
    c.stroke()

    const r = 2.4 + fade * 2
    const g = c.createRadialGradient(cur.x, cur.y, 0, cur.x, cur.y, r * 4)
    g.addColorStop(0, rgba(col, 0.85 * fade))
    g.addColorStop(0.35, rgba(col, 0.3 * fade))
    g.addColorStop(1, 'rgba(0,0,0,0)')
    c.fillStyle = g
    c.beginPath()
    c.arc(cur.x, cur.y, r * 4, 0, Math.PI * 2)
    c.fill()

    c.fillStyle = rgba(COLOR.ice, 0.75 * fade)
    c.beginPath()
    c.arc(cur.x, cur.y, r * 0.45, 0, Math.PI * 2)
    c.fill()
  }
}

function drawWaves(c: CanvasRenderingContext2D): void {
  for (const w of waves) {
    const col = tintOf(w.tint)
    c.strokeStyle = rgba(col, 0.2 * w.life)
    c.lineWidth = 1.5 * w.life + 0.4
    c.beginPath()
    c.arc(w.x, w.y, w.r, 0, Math.PI * 2)
    c.stroke()
    if (w.r > 20) {
      c.strokeStyle = rgba(col, 0.1 * w.life)
      c.lineWidth = 0.8
      c.beginPath()
      c.arc(w.x, w.y, w.r * 0.7, 0, Math.PI * 2)
      c.stroke()
    }
  }
}

function drawBolts(c: CanvasRenderingContext2D): void {
  for (const b of bolts) {
    const col = tintOf(b.tint)
    const a = Math.max(0, b.life)
    c.strokeStyle = rgba(col, 0.55 * a)
    c.lineWidth = 1.8
    c.shadowColor = rgba(col, 0.5 * a)
    c.shadowBlur = 12
    c.beginPath()
    b.points.forEach((pt, i) => (i === 0 ? c.moveTo(pt.x, pt.y) : c.lineTo(pt.x, pt.y)))
    c.stroke()
    c.strokeStyle = rgba(COLOR.ice, 0.45 * a)
    c.lineWidth = 0.8
    c.shadowBlur = 0
    c.beginPath()
    b.points.forEach((pt, i) => (i === 0 ? c.moveTo(pt.x, pt.y) : c.lineTo(pt.x, pt.y)))
    c.stroke()
  }
  c.shadowBlur = 0
}

function drawAgents(c: CanvasRenderingContext2D): void {
  // 远→近绘制，近处盖住远处
  const sorted = agents.slice().sort((a, b) => b.z - a.z)
  for (const n of sorted) {
    const p = project(n.x, n.y, n.z)
    const pulse = 0.5 + 0.5 * Math.sin(n.phase)
    const col = tintOf(n.tint)
    const r = n.r * p.s * (1 + pulse * (n.hub ? 0.7 : 0.45))

    const glowR = r * (n.hub ? 7 : 4.5)
    const g = c.createRadialGradient(p.x, p.y, 0, p.x, p.y, glowR)
    g.addColorStop(0, rgba(col, (n.hub ? 0.42 : 0.26) * (0.55 + pulse * 0.45)))
    g.addColorStop(0.4, rgba(col, (n.hub ? 0.14 : 0.07) * (0.5 + pulse * 0.5)))
    g.addColorStop(1, 'rgba(0,0,0,0)')
    c.fillStyle = g
    c.beginPath()
    c.arc(p.x, p.y, glowR, 0, Math.PI * 2)
    c.fill()

    if (n.hub) {
      // 双环 + 旋转弧
      c.strokeStyle = rgba(col, 0.35 + pulse * 0.3)
      c.lineWidth = 1.15
      c.beginPath()
      c.arc(p.x, p.y, r * 2.2, 0, Math.PI * 2)
      c.stroke()

      const spin = timeSec * (1.1 + n.rate * 0.35) + n.phase
      c.strokeStyle = rgba(col, 0.65)
      c.lineWidth = 1.7
      c.beginPath()
      c.arc(p.x, p.y, r * 3.0, spin, spin + 1.2)
      c.stroke()
      c.beginPath()
      c.arc(p.x, p.y, r * 3.0, spin + Math.PI, spin + Math.PI + 0.8)
      c.stroke()

      // 卫星点
      for (let s = 0; s < 3; s++) {
        const ang = n.orbit + (s * Math.PI * 2) / 3
        const rad = r * 3.9
        const sx = p.x + Math.cos(ang) * rad
        const sy = p.y + Math.sin(ang) * rad * 0.72
        c.fillStyle = rgba(col, 0.7)
        c.beginPath()
        c.arc(sx, sy, 1.4, 0, Math.PI * 2)
        c.fill()
      }
    }

    c.fillStyle = rgba(col, n.hub ? 0.95 : 0.8)
    c.beginPath()
    c.arc(p.x, p.y, r, 0, Math.PI * 2)
    c.fill()

    c.fillStyle = rgba(COLOR.ice, n.hub ? 0.5 : 0.28)
    c.beginPath()
    c.arc(p.x - r * 0.28, p.y - r * 0.28, r * 0.32, 0, Math.PI * 2)
    c.fill()
  }
}

/** 中央推理核心 —— 全息多环体 */
function drawCore(c: CanvasRenderingContext2D): void {
  const cx = width * (0.5 + (pointerX - 0.5) * 0.03)
  const cy = height * (0.42 + (pointerY - 0.5) * 0.02)
  const base = Math.min(width, height) * 0.09
  const breath = 0.5 + 0.5 * Math.sin(timeSec * 0.8)

  // 核心体光
  const coreGlow = c.createRadialGradient(cx, cy, 0, cx, cy, base * 3.2)
  coreGlow.addColorStop(0, rgba(COLOR.cyan, 0.16 + breath * 0.06))
  coreGlow.addColorStop(0.35, rgba(COLOR.auroraBlue, 0.08))
  coreGlow.addColorStop(1, 'rgba(0,0,0,0)')
  c.fillStyle = coreGlow
  c.beginPath()
  c.arc(cx, cy, base * 3.2, 0, Math.PI * 2)
  c.fill()

  // 椭圆轨道环（伪 3D）
  for (let i = 0; i < 3; i++) {
    const tilt = 0.35 + i * 0.12
    const rot = timeSec * (0.35 + i * 0.12) * (i % 2 ? -1 : 1)
    const rx = base * (1.6 + i * 0.55)
    const ry = rx * tilt
    const col = i === 1 ? COLOR.oatGold : i === 0 ? COLOR.cyan : COLOR.auroraBlue

    c.save()
    c.translate(cx, cy)
    c.rotate(rot * 0.25)
    c.strokeStyle = rgba(col, 0.28 + breath * 0.12)
    c.lineWidth = 1.2
    c.beginPath()
    c.ellipse(0, 0, rx, ry, rot, 0, Math.PI * 2)
    c.stroke()

    // 环上运行指示点
    const ang = timeSec * (1.2 + i * 0.4) + i
    const px = Math.cos(ang + rot) * rx
    const py = Math.sin(ang + rot) * ry
    const pg = c.createRadialGradient(px, py, 0, px, py, 10)
    pg.addColorStop(0, rgba(col, 0.85))
    pg.addColorStop(1, 'rgba(0,0,0,0)')
    c.fillStyle = pg
    c.beginPath()
    c.arc(px, py, 10, 0, Math.PI * 2)
    c.fill()
    c.restore()
  }

  // 内核
  const kernel = c.createRadialGradient(cx, cy, 0, cx, cy, base * 0.55)
  kernel.addColorStop(0, rgba(COLOR.ice, 0.55))
  kernel.addColorStop(0.4, rgba(COLOR.cyan, 0.35))
  kernel.addColorStop(1, rgba(COLOR.auroraBlue, 0.05))
  c.fillStyle = kernel
  c.beginPath()
  c.arc(cx, cy, base * (0.45 + breath * 0.08), 0, Math.PI * 2)
  c.fill()

  // 六边形核心外壳
  c.strokeStyle = rgba(COLOR.cyan, 0.4 + breath * 0.2)
  c.lineWidth = 1.4
  c.beginPath()
  const hr = base * (0.85 + breath * 0.06)
  for (let k = 0; k < 6; k++) {
    const ang = (Math.PI / 3) * k + timeSec * 0.15
    const x = cx + Math.cos(ang) * hr
    const y = cy + Math.sin(ang) * hr
    if (k === 0) c.moveTo(x, y)
    else c.lineTo(x, y)
  }
  c.closePath()
  c.stroke()
}

function drawScanBeam(c: CanvasRenderingContext2D): void {
  const cycle = ((timeSec * 0.07) % 1.15) / 1.15
  const y = height * (0.06 + cycle * 0.88)
  const bandH = Math.max(26, height * 0.038)
  const grad = c.createLinearGradient(0, y - bandH, 0, y + bandH)
  grad.addColorStop(0, 'rgba(0,0,0,0)')
  grad.addColorStop(0.45, rgba(COLOR.cyan, 0.04))
  grad.addColorStop(0.5, rgba(COLOR.auroraBlue, 0.09))
  grad.addColorStop(0.55, rgba(COLOR.cyan, 0.04))
  grad.addColorStop(1, 'rgba(0,0,0,0)')
  c.fillStyle = grad
  c.fillRect(0, y - bandH, width, bandH * 2)

  c.strokeStyle = rgba(COLOR.cyan, 0.16)
  c.lineWidth = 1
  c.beginPath()
  c.moveTo(0, y)
  // 轻微波形扫描线
  for (let x = 0; x <= width; x += 16) {
    c.lineTo(x, y + Math.sin(x * 0.04 + timeSec * 4) * 2.5)
  }
  c.stroke()
}

function drawVignetteHints(c: CanvasRenderingContext2D): void {
  // 四角微 HUD 角标（极克制）
  const len = Math.min(28, width * 0.03)
  const pad = 18
  const corners = [
    [pad, pad, 1, 1],
    [width - pad, pad, -1, 1],
    [pad, height - pad, 1, -1],
    [width - pad, height - pad, -1, -1]
  ] as const
  c.strokeStyle = rgba(COLOR.cyan, 0.18)
  c.lineWidth = 1
  for (const [x, y, sx, sy] of corners) {
    c.beginPath()
    c.moveTo(x, y + sy * len)
    c.lineTo(x, y)
    c.lineTo(x + sx * len, y)
    c.stroke()
  }
}

function draw(): void {
  if (!ctx) return
  const c = ctx
  c.clearRect(0, 0, width, height)

  c.globalCompositeOperation = 'source-over'
  drawHorizon(c)
  drawHexLattice(c)

  c.globalCompositeOperation = 'lighter'
  drawVolumetricOrbs(c)
  drawEnergyBands(c)
  drawDust(c)
  drawLinks(c)
  drawWaves(c)
  drawPhotons(c)
  drawBolts(c)
  drawAgents(c)
  drawCore(c)
  drawScanBeam(c)

  c.globalCompositeOperation = 'source-over'
  drawVignetteHints(c)
}

// ─────────────────────────────────────────────
//  主循环 / 自适应画质
// ─────────────────────────────────────────────
function loop(ts: number): void {
  if (!running) {
    rafId.value = null
    return
  }
  const elapsed = ts - lastTs
  if (elapsed >= FRAME_MS) {
    const t0 = performance.now()
    const dt = Math.min(elapsed / 1000, 0.05)
    lastTs = ts - (elapsed % FRAME_MS)
    step(dt)
    draw()
    const cost = performance.now() - t0
    frameBudgetEma = frameBudgetEma * 0.9 + cost * 0.1
    // 单帧绘制超过 ~22ms 则降质，低于 ~12ms 回升
    if (frameBudgetEma > 22 && quality > 0.65) quality = Math.max(0.65, quality - 0.05)
    else if (frameBudgetEma < 12 && quality < 1) quality = Math.min(1, quality + 0.03)
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

  ctx = canvas.getContext('2d', { alpha: true })
  ctx?.setTransform(dpr, 0, 0, dpr, 0, 0)

  rebuild()
  if (!running) draw()
}

function handleVisibility(): void {
  if (document.hidden) stop()
  else start()
}

function handlePointer(e: PointerEvent): void {
  pointerTx = e.clientX / (window.innerWidth || 1)
  pointerTy = e.clientY / (window.innerHeight || 1)
}

onMounted(() => {
  resize()
  const canvas = canvasRef.value
  if (canvas?.parentElement) {
    resizeObserver = new ResizeObserver(() => resize())
    resizeObserver.observe(canvas.parentElement)
  }
  document.addEventListener('visibilitychange', handleVisibility)
  window.addEventListener('pointermove', handlePointer, { passive: true })
  start()
})

onUnmounted(() => {
  stop()
  resizeObserver?.disconnect()
  resizeObserver = null
  ctx = null
  agents = []
  dust = []
  photons = []
  waves = []
  bolts = []
  edges = []
  hexCells = []
  document.removeEventListener('visibilitychange', handleVisibility)
  window.removeEventListener('pointermove', handlePointer)
})
</script>

<template>
  <div class="cog-aura-bg" aria-hidden="true">
    <canvas ref="canvasRef" class="cog-aura-canvas" :style="{ opacity: props.opacity }" />
    <div class="cog-aura-veil" />
    <div class="cog-aura-grain" />
  </div>
</template>

<style scoped>
.cog-aura-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.cog-aura-canvas {
  display: block;
  width: 100%;
  height: 100%;
  transition: opacity 0.6s ease;
}

.cog-aura-veil {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(
      ellipse 50% 46% at 50% 44%,
      rgba(8, 10, 18, 0.48) 0%,
      rgba(8, 10, 18, 0.18) 58%,
      rgba(8, 10, 18, 0) 100%
    ),
    radial-gradient(ellipse 90% 70% at 50% 100%, rgba(6, 10, 22, 0.35) 0%, transparent 55%);
}

/* 极轻胶片噪点，压住数码感 */
.cog-aura-grain {
  position: absolute;
  inset: 0;
  opacity: 0.035;
  mix-blend-mode: overlay;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

@media (prefers-reduced-motion: reduce) {
  .cog-aura-canvas {
    opacity: 0.45 !important;
  }
}
</style>
