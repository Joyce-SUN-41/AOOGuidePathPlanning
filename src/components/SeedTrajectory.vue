<script setup lang="ts">
/**
 * SeedTrajectory.vue — AOO 种子粒子轨迹动画组件
 *
 * 模拟论文 Figure 5 的搜索轨迹效果，展示 AOO 种子在解空间中的运动：
 *   - 探索阶段 (0-30%):  粒子大面积扩散（风/水/动物传播）
 *   - 滚动阶段 (30-70%): 粒子向最优区域螺旋聚拢（湿敏滚动）
 *   - 弹射阶段 (70-100%):粒子精准弹射搜索（储能弹射）
 *
 * 支持 2D (ECharts scatter+lines) 和 3D (echarts-gl scatter3D) 两种视图。
 */
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption, ScatterSeriesOption } from 'echarts'
import {
  CaretRightOutlined,
  PauseCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  GlobalOutlined,
  NodeIndexOutlined,
  CompassOutlined,
  RocketOutlined,
} from '@ant-design/icons-vue'
import type { AOOConvergenceData } from '@/types/aoo'

// ═══════════════════════════════════════════
// Types
// ═══════════════════════════════════════════

type SeedPhase = 'exploration' | 'rolling' | 'ejection'
type ViewMode = '2d' | '3d'

interface InterpolatedFrame {
  iteration: number
  phaseRatio: number
  phase: SeedPhase
  positions: [number, number][]
  bestIndex: number
  diversity: number
}

interface TrailEntry {
  x: number
  y: number
  age: number     // frames since this entry was current
  phase: SeedPhase
  phaseRatio: number
}

// ═══════════════════════════════════════════
// Props & Emits
// ═══════════════════════════════════════════

const props = withDefaults(
  defineProps<{
    convergenceData: AOOConvergenceData
    autoPlay?: boolean
    height?: number
    showControls?: boolean
    trailLength?: number
    defaultView?: ViewMode
  }>(),
  {
    autoPlay: true,
    height: 520,
    showControls: true,
    trailLength: 12,
    defaultView: '2d',
  }
)

const emit = defineEmits<{
  (e: 'frameChange', iteration: number, phase: SeedPhase, diversity: number): void
  (e: 'complete'): void
  (e: 'phaseChange', phase: SeedPhase, iteration: number): void
  (e: 'playStateChange', playing: boolean): void
}>()

// ═══════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════

const PHASE_CONFIG: Record<SeedPhase, {
  name: string
  range: [number, number]
  color: string
  gradient: string[]
  icon: typeof CompassOutlined
  description: string
}> = {
  exploration: {
    name: '探索扩散',
    range: [0, 0.3],
    color: '#FF8C42',
    gradient: ['#FF6B35', '#FF8C42', '#FFB347', '#FFD700'],
    icon: CompassOutlined,
    description: '风/水/动物传播：种群在全局空间大面积扩散搜索',
  },
  rolling: {
    name: '湿敏滚动',
    range: [0.3, 0.7],
    color: '#4F7CFF',
    gradient: ['#3366FF', '#4F7CFF', '#6B9FFF', '#7BB8FF'],
    icon: NodeIndexOutlined,
    description: '螺旋逼近：个体沿最优方向滚动，逐步收敛聚合',
  },
  ejection: {
    name: '储能弹射',
    range: [0.7, 1.0],
    color: '#A855F7',
    gradient: ['#7C3AED', '#A855F7', '#C084FC', '#FF4D4F'],
    icon: RocketOutlined,
    description: '高精度弹射：在最优区域附近进行精细局部搜索',
  },
}

const SPEED_OPTIONS = [
  { label: '0.5x', value: 0.5 },
  { label: '1x', value: 1 },
  { label: '2x', value: 2 },
  { label: '4x', value: 4 },
] as const

/** 每对快照间的插值步数 */
const INTERP_STEPS = 18
/** 每帧最大拖尾帧数 */
const MAX_TRAIL_AGE = computed(() => props.trailLength)

/** 根据进度比获取阶段 */
function getPhase(ratio: number): SeedPhase {
  if (ratio <= 0.3) return 'exploration'
  if (ratio <= 0.7) return 'rolling'
  return 'ejection'
}

// ═══════════════════════════════════════════
// Reactive State
// ═══════════════════════════════════════════

const viewMode = ref<ViewMode>(props.defaultView)
const isPlaying = ref(props.autoPlay)
const hasCompleted = ref(false)
const currentSpeed = ref<number>(1)

const chart2DContainer = ref<HTMLDivElement | null>(null)
const chart3DContainer = ref<HTMLDivElement | null>(null)
let chart2D: echarts.ECharts | null = null
let chart3D: echarts.ECharts | null = null
let echartsGL3DLoaded = false

let resizeObserver2D: ResizeObserver | null = null
let resizeObserver3D: ResizeObserver | null = null

/** 预计算的插值帧数组 */
let frames: InterpolatedFrame[] = []
/** 当前帧索引 */
let frameIndex = 0
/** 拖尾历史（最近 N 帧的粒子位置） */
let trailBuffer: TrailEntry[][] = []

let rafId: number | null = null
let lastFrameTimeMs = 0
const TARGET_FPS = 30

/** 当前渲染帧的响应式快照 */
const currentIteration = ref(0)
const currentPhase = ref<SeedPhase>('exploration')
const currentDiversity = ref(0)
const currentBestIndex = ref(-1)

// ═══════════════════════════════════════════
// Computed
// ═══════════════════════════════════════════

const totalFrames = computed(() => frames.length)
const progressPercent = computed(() => {
  if (totalFrames.value <= 1) return 0
  return Math.round((frameIndex / (totalFrames.value - 1)) * 100)
})
const totalIterations = computed(() => props.convergenceData.iterations.at(-1) ?? 0)
const metadata = computed(() => props.convergenceData.metadata)
const populationSize = computed(() => metadata.value?.populationSize ?? 0)

const previousPhase = ref<SeedPhase | null>(null)

// ═══════════════════════════════════════════
// Warm/Cool Color Interpolation
// ═══════════════════════════════════════════

/** 根据 phaseRatio (0-1) 计算渐变色：暖色(0) → 冷色(0.5) → 热色(1) */
function getPhaseColor(ratio: number): string {
  // 使用分段 HSL 插值保证视觉连续性
  if (ratio <= 0.15) {
    // 0% → 15%: 深橙 → 亮橙
    const t = ratio / 0.15
    return hslInterp(25, 25, t, 60, 30, 100, 55)
  } else if (ratio <= 0.3) {
    // 15% → 30%: 亮橙 → 金黄
    const t = (ratio - 0.15) / 0.15
    return hslInterp(30, 30, t, 55, 45, 90, 55)
  } else if (ratio <= 0.5) {
    // 30% → 50%: 金黄 → 蓝色
    const t = (ratio - 0.3) / 0.2
    return hslInterp(45, 225, t, 55, 55, 90, 100)
  } else if (ratio <= 0.7) {
    // 50% → 70%: 蓝 → 青蓝
    const t = (ratio - 0.5) / 0.2
    return hslInterp(225, 260, t, 55, 50, 100, 100)
  } else if (ratio <= 0.85) {
    // 70% → 85%: 青蓝 → 紫色
    const t = (ratio - 0.7) / 0.15
    return hslInterp(260, 285, t, 50, 45, 100, 100)
  } else {
    // 85% → 100%: 紫 → 红紫
    const t = (ratio - 0.85) / 0.15
    return hslInterp(285, 340, t, 45, 58, 100, 100)
  }
}

function hslInterp(
  h1: number, h2: number, t: number,
  s1: number, s2: number,
  l1: number, l2: number
): string {
  const h = h1 + (h2 - h1) * t
  const s = s1 + (s2 - s1) * t
  const l = l1 + (l2 - l1) * t
  return `hsl(${Math.round(h)}, ${Math.round(s)}%, ${Math.round(l)}%)`
}

/** 根据年龄计算拖尾点的透明度 (0=最新, MAX_TRAIL_AGE=最旧) */
function getTrailOpacity(age: number): number {
  const maxAge = MAX_TRAIL_AGE.value
  if (maxAge <= 0) return 0
  return Math.max(0, 0.7 * (1 - age / maxAge))
}

/** 根据年龄计算拖尾点的大小 */
function getTrailSize(age: number): number {
  const maxAge = MAX_TRAIL_AGE.value
  if (maxAge <= 0) return 3
  return 3 + (5 - 3) * (1 - age / maxAge)
}

// ═══════════════════════════════════════════
// Simple PRNG (deterministic for consistent replay)
// ═══════════════════════════════════════════

let seed = 42
function resetRNG(s = 42) { seed = s }
function random01(): number {
  seed = (seed * 16807) % 2147483647
  return (seed - 1) / 2147483646
}
function randomNormal(): number {
  // Box-Muller
  const u1 = random01() || 1e-10
  const u2 = random01()
  return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
}

// ═══════════════════════════════════════════
// Frame Precomputation
// ═══════════════════════════════════════════

function precomputeFrames(): InterpolatedFrame[] {
  const snapshots = props.convergenceData.populationSnapshots
  const iterations = props.convergenceData.iterations
  const diversityArr = props.convergenceData.diversity

  if (!snapshots || snapshots.length < 2) {
    // 只有 1 个快照时，生成单帧
    if (snapshots && snapshots.length === 1) {
      const s = snapshots[0]!
      return [{
        iteration: iterations[0] ?? 1,
        phaseRatio: 0,
        phase: 'exploration',
        positions: s.positionsX.map((x, j) => [x, s.positionsY[j]!] as [number, number]),
        bestIndex: s.bestIndex,
        diversity: diversityArr[0] ?? 1,
      }]
    }
    return []
  }

  resetRNG(42)
  const totalIter = iterations[snapshots.length - 1] ?? 500
  const result: InterpolatedFrame[] = []

  for (let i = 0; i < snapshots.length - 1; i++) {
    const s0 = snapshots[i]!
    const s1 = snapshots[i + 1]!
    const iter0 = iterations[i]!
    const iter1 = iterations[i + 1]!
    const div0 = diversityArr[i]!
    const div1 = diversityArr[i + 1]!
    const N = s0.positionsX.length

    for (let k = 0; k < INTERP_STEPS; k++) {
      const alpha = k / INTERP_STEPS
      const iter = iter0 + (iter1 - iter0) * alpha
      const phaseRatio = totalIter > 0 ? iter / totalIter : 0
      const phase = getPhase(phaseRatio)
      const diversity = div0 + (div1 - div0) * alpha

      const positions: [number, number][] = []
      const bestIdx = s0.bestIndex

      // 噪声幅度随收敛因子衰减: amplitude = 0.04 * (1 - phaseRatio)² * (1 - alpha)²
      const noiseAmplitude = 0.04 * Math.pow(1 - phaseRatio, 2) * Math.pow(1 - alpha, 2)

      for (let j = 0; j < N; j++) {
        // 线性插值基础位置
        let x = s0.positionsX[j]! + (s1.positionsX[j]! - s0.positionsX[j]!) * alpha
        let y = s0.positionsY[j]! + (s1.positionsY[j]! - s0.positionsY[j]!) * alpha

        const targetBestX = s1.positionsX[bestIdx]!
        const targetBestY = s1.positionsY[bestIdx]!

        if (phase === 'exploration') {
          // ── 探索阶段：大面积扩散（Lévy-like 随机游走） ──
          const levyNoise = noiseAmplitude * (Math.random() < 0.3 ? 3 : 1)
          x += randomNormal() * levyNoise
          y += randomNormal() * levyNoise
        } else if (phase === 'rolling') {
          // ── 滚动阶段：螺旋向最优聚拢 ──
          const dx = targetBestX - x
          const dy = targetBestY - y
          const dist = Math.sqrt(dx * dx + dy * dy) + 1e-8
          const spiralAngle = alpha * Math.PI * 4  // 2 圈螺旋
          const sinA = Math.sin(spiralAngle)

          // 螺旋偏移（垂直于最优方向）
          const nx = -dy / dist
          const ny = dx / dist
          const spiralStrength = noiseAmplitude * 3 * (1 - alpha)
          x += nx * sinA * spiralStrength + dx / dist * noiseAmplitude * 0.5
          y += ny * sinA * spiralStrength + dy / dist * noiseAmplitude * 0.5

          // 小量随机扰动
          x += randomNormal() * noiseAmplitude * 0.3
          y += randomNormal() * noiseAmplitude * 0.3
        } else {
          // ── 弹射阶段：精准弹跳搜索 ──
          const dx = targetBestX - x
          const dy = targetBestY - y
          const dist = Math.sqrt(dx * dx + dy * dy)

          if (dist > 0.01 && Math.random() < 0.08) {
            // 8% 概率弹射跳向最优区域
            const jumpRatio = 0.3 + random01() * 0.5
            x += dx * jumpRatio
            y += dy * jumpRatio
          } else {
            // 精细局部搜索
            x += randomNormal() * noiseAmplitude * 0.15
            y += randomNormal() * noiseAmplitude * 0.15
          }
        }

        // 边界裁剪 [0, 1]
        positions.push([Math.max(0, Math.min(1, x)), Math.max(0, Math.min(1, y))])
      }

      result.push({ iteration: iter, phaseRatio, phase, positions, bestIndex: bestIdx, diversity })
    }
  }

  // 追加最后一帧（准确快照位置）
  const last = snapshots[snapshots.length - 1]!
  result.push({
    iteration: totalIter,
    phaseRatio: 1,
    phase: 'ejection',
    positions: last.positionsX.map((x, j) => [x, last.positionsY[j]!] as [number, number]),
    bestIndex: last.bestIndex,
    diversity: diversityArr[snapshots.length - 1] ?? 0,
  })

  return result
}

// ═══════════════════════════════════════════
// Trail Buffer Management
// ═══════════════════════════════════════════

function initTrailBuffer(frameCount: number): void {
  trailBuffer = new Array(frameCount)
}

function updateTrailBuffer(idx: number, frame: InterpolatedFrame): void {
  const entries: TrailEntry[] = frame.positions.map((pos) => ({
    x: pos[0],
    y: pos[1],
    age: 0,
    phase: frame.phase,
    phaseRatio: frame.phaseRatio,
  }))
  trailBuffer[idx] = entries

  // 递增已有条目的年龄
  const maxAge = MAX_TRAIL_AGE.value
  const start = Math.max(0, idx - maxAge)
  for (let i = start; i < idx; i++) {
    const buf = trailBuffer[i]
    if (buf) {
      for (const entry of buf) {
        entry.age = idx - i
      }
    }
  }
}

// ═══════════════════════════════════════════
// 2D Chart
// ═══════════════════════════════════════════

function init2DChart(): void {
  if (!chart2DContainer.value) return
  chart2D?.dispose()
  chart2D = echarts.init(chart2DContainer.value, undefined, {
    devicePixelRatio: Math.min(window.devicePixelRatio || 1, 2),
  })
  resizeObserver2D = new ResizeObserver(() => chart2D?.resize())
  resizeObserver2D.observe(chart2DContainer.value)
}

function render2DFrame(frame: InterpolatedFrame): void {
  if (!chart2D) return

  const idx = frameIndex
  const maxAge = MAX_TRAIL_AGE.value

  // ── 构建拖尾数据 ──
  const trailScatterData: {
    value: [number, number]
    symbolSize: number
    itemStyle: { color: string; opacity: number }
  }[] = []

  const trailStart = Math.max(0, idx - maxAge)
  for (let t = trailStart; t < idx; t++) {
    const buf = trailBuffer[t]
    if (!buf) continue
    for (const entry of buf) {
      if (entry.age === 0) continue  // skip current (rendered separately)
      trailScatterData.push({
        value: [entry.x, entry.y],
        symbolSize: getTrailSize(entry.age),
        itemStyle: {
          color: getPhaseColor(entry.phaseRatio),
          opacity: getTrailOpacity(entry.age),
        },
      })
    }
  }

  // ── 当前帧粒子数据 ──
  const currentScatterData: {
    value: [number, number]
    symbolSize: number
    itemStyle: { color: string; borderColor: string; borderWidth: number; shadowBlur: number; shadowColor: string }
  }[] = []

  for (let j = 0; j < frame.positions.length; j++) {
    const [x, y] = frame.positions[j]!
    const isBest = j === frame.bestIndex
    const color = getPhaseColor(frame.phaseRatio)
    currentScatterData.push({
      value: [x, y],
      symbolSize: isBest ? 16 : 8,
      itemStyle: {
        color: isBest ? '#FFFFFF' : color,
        borderColor: isBest ? color : color,
        borderWidth: isBest ? 3 : 1.5,
        shadowBlur: isBest ? 12 : 0,
        shadowColor: isBest ? color : 'transparent',
      },
    })
  }

  // ── 最优个体历史轨迹（折线） ──
  const bestTrajectoryData: [number, number][] = []
  const traceStart = Math.max(0, idx - maxAge * 3)
  for (let t = traceStart; t <= idx; t++) {
    if (t < frames.length && trailBuffer[t] && frames[t]) {
      const entry = trailBuffer[t]![frames[t]!.bestIndex]
      if (entry) {
        bestTrajectoryData.push([entry.x, entry.y])
      }
    }
  }

  const option: EChartsOption = {
    animation: false,  // 逐帧渲染，无需入场动画

    backgroundColor: 'transparent',

    tooltip: {
      trigger: 'item' as const,
      backgroundColor: 'rgba(30, 30, 30, 0.88)',
      borderColor: '#444',
      textStyle: { color: '#eee', fontSize: 12 },
      formatter: (params: any) => {
        if (!params.value || params.value.length < 2) return ''
        const [x, y] = params.value
        return `${params.seriesName}<br/>X: ${x.toFixed(3)}<br/>Y: ${y.toFixed(3)}`
      },
    } as any,

    grid: {
      top: 16,
      right: 20,
      bottom: 16,
      left: 20,
      containLabel: false,
    },

    xAxis: {
      type: 'value' as const,
      min: -0.05,
      max: 1.05,
      show: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#A8A6A2', fontSize: 10 },
      splitLine: { show: true, lineStyle: { color: 'rgba(0,0,0,0.04)', type: 'dashed' } },
    },

    yAxis: {
      type: 'value' as const,
      min: -0.05,
      max: 1.05,
      show: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#A8A6A2', fontSize: 10 },
      splitLine: { show: true, lineStyle: { color: 'rgba(0,0,0,0.04)', type: 'dashed' } },
    },

    series: [
      // ① 拖尾轨迹
      {
        name: '粒子轨迹',
        type: 'scatter' as const,
        data: trailScatterData as any,
        emphasis: { scale: 1.3 },
        zlevel: 0,
      } as ScatterSeriesOption,
      // ② 最优个体历史轨迹线
      {
        name: '最优轨迹',
        type: 'line' as const,
        data: bestTrajectoryData,
        smooth: true,
        symbol: 'none',
        lineStyle: {
          color: 'rgba(255, 255, 255, 0.7)',
          width: 2.5,
          shadowBlur: 6,
          shadowColor: 'rgba(0,0,0,0.3)',
        },
        zlevel: 1,
      },
      // ③ 当前种群粒子
      {
        name: '种群粒子',
        type: 'scatter' as const,
        data: currentScatterData as any,
        emphasis: { scale: 1.5 },
        zlevel: 3,
      } as ScatterSeriesOption,
    ] as EChartsOption['series'],
  }

  chart2D.setOption(option, { notMerge: true, lazyUpdate: false })
}

// ═══════════════════════════════════════════
// 3D Chart (echarts-gl)
// ═══════════════════════════════════════════

async function init3DChart(): Promise<boolean> {
  if (!chart3DContainer.value) return false
  if (echartsGL3DLoaded && chart3D) return true

  try {
    // 动态加载 echarts-gl（scatter3D 等组件会挂载到全局 echarts）
    await import('echarts-gl')
    echartsGL3DLoaded = true
  } catch {
    console.warn('[SeedTrajectory] echarts-gl 加载失败，3D 视图不可用')
    return false
  }

  chart3D?.dispose()
  chart3D = echarts.init(chart3DContainer.value, undefined, {
    devicePixelRatio: Math.min(window.devicePixelRatio || 1, 2),
  })
  resizeObserver3D = new ResizeObserver(() => chart3D?.resize())
  resizeObserver3D.observe(chart3DContainer.value)
  return true
}

function render3DFrame(frame: InterpolatedFrame): void {
  if (!chart3D || !echartsGL3DLoaded) return

  const data: [number, number, number][] = []
  const colorList: string[] = []

  for (let j = 0; j < frame.positions.length; j++) {
    const [x, y] = frame.positions[j]!
    // Z 轴 = 适应度（若无则用相位比模拟）
    const z = frame.phaseRatio + frame.diversity * 0.3 * (1 - frame.phaseRatio)
    data.push([x, y, Math.max(0, Math.min(1, z))])
    colorList.push(frame.bestIndex === j ? '#FFFFFF' : getPhaseColor(frame.phaseRatio))
  }

  const option: any = {
    animation: false,
    backgroundColor: 'transparent',

    grid3D: {
      viewControl: {
        autoRotate: isPlaying.value,
        autoRotateSpeed: 2,
        distance: 180,
        alpha: 35,
        beta: 45,
      },
      boxWidth: 100,
      boxHeight: 100,
      boxDepth: 60,
    },

    xAxis3D: { type: 'value', min: -0.05, max: 1.05, name: '维度 1' },
    yAxis3D: { type: 'value', min: -0.05, max: 1.05, name: '维度 2' },
    zAxis3D: { type: 'value', min: 0, max: 1, name: '适应度' },

    series: [
      {
        type: 'scatter3D',
        data: data.map((d, i) => ({
          value: d,
          itemStyle: {
            color: colorList[i],
            borderColor: frame.bestIndex === i ? getPhaseColor(frame.phaseRatio) : 'transparent',
            borderWidth: frame.bestIndex === i ? 2 : 0,
            opacity: 0.85,
          },
        })),
        symbolSize: (_value: number[], params: { dataIndex: number }) =>
          frame.bestIndex === params.dataIndex ? 12 : 6,
      },
    ],
  }

  chart3D.setOption(option, { notMerge: true, lazyUpdate: false })
}

// ═══════════════════════════════════════════
// Render Current Frame (dispatches to active view)
// ═══════════════════════════════════════════

function renderFrame(): void {
  if (frames.length === 0) return
  const idx = Math.min(frameIndex, frames.length - 1)
  const frame = frames[idx]!
  if (!frame) return

  // 更新响应式状态
  currentIteration.value = Math.round(frame.iteration)
  currentPhase.value = frame.phase
  currentDiversity.value = frame.diversity
  currentBestIndex.value = frame.bestIndex

  // 阶段切换回调
  if (previousPhase.value !== frame.phase) {
    previousPhase.value = frame.phase
    emit('phaseChange', frame.phase, currentIteration.value)
  }

  // 更新拖尾缓冲
  updateTrailBuffer(idx, frame)

  // 渲染到活跃视图
  if (viewMode.value === '3d') {
    render3DFrame(frame)
  } else {
    render2DFrame(frame)
  }

  emit('frameChange', currentIteration.value, frame.phase, frame.diversity)
}

// ═══════════════════════════════════════════
// Animation Loop (requestAnimationFrame)
// ═══════════════════════════════════════════

function getFrameIntervalMs(): number {
  return (1000 / TARGET_FPS) / currentSpeed.value
}

function animationLoop(timestamp: number): void {
  if (!isPlaying.value || frames.length <= 1) {
    rafId = null
    return
  }

  const interval = getFrameIntervalMs()
  const elapsed = timestamp - lastFrameTimeMs

  if (elapsed >= interval) {
    // 可能跳过多个帧（高速模式下）
    const framesToAdvance = Math.max(1, Math.floor(elapsed / interval))
    lastFrameTimeMs = timestamp - (elapsed % interval)

    const newIndex = Math.min(frameIndex + framesToAdvance, frames.length - 1)
    frameIndex = newIndex
    renderFrame()

    if (frameIndex >= frames.length - 1) {
      hasCompleted.value = true
      isPlaying.value = false
      emit('playStateChange', false)
      emit('complete')
      rafId = null
      return
    }
  }

  rafId = requestAnimationFrame(animationLoop)
}

function startAnimation(): void {
  if (rafId || frames.length <= 1) return
  lastFrameTimeMs = performance.now()
  rafId = requestAnimationFrame(animationLoop)
}

function stopAnimation(): void {
  if (rafId) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
}

// ═══════════════════════════════════════════
// Control Methods
// ═══════════════════════════════════════════

function play(): void {
  if (isPlaying.value || frames.length <= 1) return
  if (hasCompleted.value) {
    hasCompleted.value = false
    frameIndex = 0
    renderFrame()
  }
  isPlaying.value = true
  emit('playStateChange', true)
  startAnimation()
}

function pause(): void {
  if (!isPlaying.value) return
  isPlaying.value = false
  emit('playStateChange', false)
  stopAnimation()
}

function togglePlayPause(): void {
  if (isPlaying.value) pause()
  else play()
}

function seekTo(index: number): void {
  const wasPlaying = isPlaying.value
  if (wasPlaying) stopAnimation()
  frameIndex = Math.max(0, Math.min(index, frames.length - 1))
  renderFrame()
  if (wasPlaying) startAnimation()
}

function replay(): void {
  stopAnimation()
  hasCompleted.value = false
  frameIndex = 0
  renderFrame()
  isPlaying.value = true
  emit('playStateChange', true)
  startAnimation()
}

function setSpeed(sp: number): void {
  currentSpeed.value = sp
}

function switchView(mode: ViewMode): void {
  if (mode === viewMode.value) return
  viewMode.value = mode

  nextTick(async () => {
    if (mode === '3d') {
      const ok = await init3DChart()
      if (!ok) {
        viewMode.value = '2d'
        return
      }
    } else {
      if (!chart2D) init2DChart()
    }
    renderFrame()
  })
}

// ═══════════════════════════════════════════
// Data Watcher
// ═══════════════════════════════════════════

watch(
  () => props.convergenceData,
  (newData) => {
    if (!newData || newData.iterations.length === 0) {
      frames = []
      initTrailBuffer(0)
      return
    }

    stopAnimation()

    // 预计算插值帧
    frames = precomputeFrames()
    initTrailBuffer(frames.length)
    frameIndex = 0
    hasCompleted.value = false
    previousPhase.value = null

    nextTick(() => {
      if (!chart2D) init2DChart()
      if (viewMode.value === '3d') init3DChart()
      renderFrame()

      if (props.autoPlay) {
        isPlaying.value = true
        emit('playStateChange', true)
        startAnimation()
      }
    })
  },
  { immediate: true, deep: false }
)

// ═══════════════════════════════════════════
// View Mode Watcher (re-init on switch)
// ═══════════════════════════════════════════

watch(viewMode, async (mode) => {
  if (mode === '3d' && !echartsGL3DLoaded) {
    await init3DChart()
  }
  if (mode === '2d' && !chart2D) {
    init2DChart()
  }
  renderFrame()
})

// ═══════════════════════════════════════════
// Lifecycle
// ═══════════════════════════════════════════

function handleVisibilityChange(): void {
  if (document.hidden && isPlaying.value) {
    pause()
  }
}

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  stopAnimation()
  resizeObserver2D?.disconnect()
  resizeObserver3D?.disconnect()
  chart2D?.dispose()
  chart3D?.dispose()
  chart2D = null
  chart3D = null
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})

// ═══════════════════════════════════════════
// Expose
// ═══════════════════════════════════════════

defineExpose({
  play,
  pause,
  togglePlayPause,
  seekTo,
  replay,
  setSpeed,
  switchView,
  viewMode,
  isPlaying,
  currentSpeed,
  currentIteration,
  currentPhase,
  currentFrameIndex: computed(() => frameIndex),
  totalFrames,
})
</script>

<template>
  <div class="seed-trajectory">
    <!-- ── 阶段指示器 ── -->
    <div class="st-phase-bar">
      <div class="phase-indicator">
        <template v-for="(cfg, key) in PHASE_CONFIG" :key="key">
          <div
            class="phase-segment"
            :class="{
              'phase-segment--active': currentPhase === key,
              'phase-segment--past': PHASE_CONFIG[currentPhase].range[0] >= cfg.range[1],
            }"
          >
            <div class="phase-segment__icon">
              <component :is="cfg.icon" />
            </div>
            <span class="phase-segment__label">{{ cfg.name }}</span>
          </div>
          <div
            v-if="key !== 'ejection'"
            class="phase-connector"
            :class="{ 'phase-connector--past': PHASE_CONFIG[currentPhase].range[0] > cfg.range[1] }"
          />
        </template>
      </div>

      <!-- 当前阶段描述 -->
      <div class="phase-desc">
        <div class="phase-desc__badge" :style="{ background: PHASE_CONFIG[currentPhase].color }">
          {{ PHASE_CONFIG[currentPhase].name }}
        </div>
        <p class="phase-desc__text">{{ PHASE_CONFIG[currentPhase].description }}</p>
      </div>
    </div>

    <!-- ── 图表区域 ── -->
    <div class="st-chart-area" :style="{ height: `${height}px` }">
      <!-- 2D 视图 -->
      <div
        v-show="viewMode === '2d'"
        ref="chart2DContainer"
        class="st-chart st-chart--2d"
      />
      <!-- 3D 视图 -->
      <div
        v-show="viewMode === '3d'"
        ref="chart3DContainer"
        class="st-chart st-chart--3d"
      />

      <!-- 空状态 -->
      <div v-if="totalFrames === 0" class="st-empty">
        <p>暂无快照数据，请先完成 AOO 优化</p>
      </div>
    </div>

    <!-- ── 播放控制栏 ── -->
    <div v-if="showControls" class="st-controls">
      <!-- 左侧：播放控制 -->
      <div class="st-controls__left">
        <button class="st-btn" title="从头播放" :disabled="totalFrames <= 1" @click="replay">
          <ReloadOutlined />
        </button>

        <button
          class="st-btn st-btn--play"
          :title="isPlaying ? '暂停' : '播放'"
          :disabled="totalFrames <= 1"
          @click="togglePlayPause"
        >
          <PauseCircleOutlined v-if="isPlaying" />
          <CaretRightOutlined v-else />
        </button>
      </div>

      <!-- 中部：进度条 -->
      <div class="st-controls__center">
        <span class="st-progress-label">{{ currentIteration }}</span>
        <div class="st-progress-track">
          <!-- 阶段分割线 -->
          <div
            class="st-progress-phase"
            :style="{ left: '0%', width: '30%', background: '#ff8c4240' }"
          />
          <div
            class="st-progress-phase"
            :style="{ left: '30%', width: '40%', background: '#4f7cff40' }"
          />
          <div
            class="st-progress-phase"
            :style="{ left: '70%', width: '30%', background: '#a855f740' }"
          />
          <!-- 可拖拽滑块 -->
          <input
            type="range"
            class="st-progress-slider"
            :min="0"
            :max="Math.max(totalFrames - 1, 0)"
            :value="frameIndex"
            :disabled="totalFrames <= 1"
            @input="seekTo(Number(($event.target as HTMLInputElement).value))"
          />
          <!-- 已播放填充 -->
          <div
            class="st-progress-fill"
            :style="{ width: `${progressPercent}%` }"
          />
        </div>
        <span class="st-progress-label">{{ totalIterations }}</span>
      </div>

      <!-- 右侧：速度 & 视图切换 -->
      <div class="st-controls__right">
        <!-- 速度选择 -->
        <span class="st-speed-icon"><ThunderboltOutlined /></span>
        <div class="st-speed-group">
          <button
            v-for="opt in SPEED_OPTIONS"
            :key="opt.value"
            class="st-speed-btn"
            :class="{ 'st-speed-btn--active': currentSpeed === opt.value }"
            @click="setSpeed(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>

        <!-- 2D/3D 切换 -->
        <div class="st-view-toggle">
          <button
            class="st-view-btn"
            :class="{ 'st-view-btn--active': viewMode === '2d' }"
            title="2D 视图"
            @click="switchView('2d')"
          >
            2D
          </button>
          <button
            class="st-view-btn"
            :class="{ 'st-view-btn--active': viewMode === '3d' }"
            title="3D 视图"
            @click="switchView('3d')"
          >
            <GlobalOutlined />
            3D
          </button>
        </div>
      </div>
    </div>

    <!-- ── 图例 ── -->
    <div class="st-legend">
      <div class="st-legend__phase">
        <span
          class="legend-swatch"
          :style="{ background: getPhaseColor(0.1) }"
        />
        <span>探索期</span>
      </div>
      <div class="st-legend__phase">
        <span
          class="legend-swatch"
          :style="{ background: getPhaseColor(0.5) }"
        />
        <span>滚动期</span>
      </div>
      <div class="st-legend__phase">
        <span
          class="legend-swatch"
          :style="{ background: getPhaseColor(0.9) }"
        />
        <span>弹射期</span>
      </div>
      <div class="st-legend__divider" />
      <div class="st-legend__stat">
        迭代 {{ currentIteration }}/{{ totalIterations }}
      </div>
      <div class="st-legend__stat">
        多样性 {{ (currentDiversity * 100).toFixed(0) }}%
      </div>
      <div v-if="populationSize" class="st-legend__stat">
        粒子 {{ populationSize }}
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════ Container ═══════════ */
.seed-trajectory {
  width: 100%;
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 16px;
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.06),
    0 2px 8px rgba(0, 0, 0, 0.03);
  overflow: hidden;
}

/* ═══════════ Phase Bar ═══════════ */
.st-phase-bar {
  padding: 14px 20px 0;
}

.phase-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
}

.phase-segment {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 8px;
  transition: all 350ms cubic-bezier(0.4, 0, 0.2, 1);
  opacity: 0.45;
}

.phase-segment--active {
  opacity: 1;
  background: rgba(79, 124, 255, 0.06);
  box-shadow: 0 0 0 1px rgba(79, 124, 255, 0.12);
}

.phase-segment--past {
  opacity: 0.25;
}

.phase-segment__icon {
  font-size: 16px;
  color: #94A3B8;
  display: flex;
  align-items: center;
}

.phase-segment--active .phase-segment__icon {
  color: #D4A373;
}

.phase-segment__label {
  font-size: 13px;
  font-weight: 500;
  color: #94A3B8;
  white-space: nowrap;
}

.phase-segment--active .phase-segment__label {
  color: #D4A373;
  font-weight: 600;
}

.phase-connector {
  width: 24px;
  height: 2px;
  background: #E8E0D8;
  border-radius: 1px;
  flex-shrink: 0;
  margin: 0 4px;
}

.phase-connector--past {
  background: #D6D4D0;
  opacity: 0.4;
}

/* Phase Description */
.phase-desc {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding: 0 4px;
}

.phase-desc__badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 99px;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.phase-desc__text {
  margin: 0;
  font-size: 12px;
  color: #82807C;
  line-height: 1.4;
}

/* ═══════════ Chart Area ═══════════ */
.st-chart-area {
  position: relative;
  width: 100%;
  min-height: 320px;
}

.st-chart {
  position: absolute;
  inset: 0;
}

.st-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #A8A6A2;
  font-size: 14px;
}

/* ═══════════ Controls ═══════════ */
.st-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 20px 10px;
  border-top: 1px solid rgba(0, 0, 0, 0.04);
}

.st-controls__left {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

/* Buttons */
.st-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid #E8E0D8;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.6);
  color: #5C5A57;
  cursor: pointer;
  font-size: 14px;
  transition: background 150ms, border-color 150ms, color 150ms, transform 100ms;
}

.st-btn:hover:not(:disabled) {
  background: rgba(79, 124, 255, 0.08);
  border-color: #B8CBFF;
  color: #4F7CFF;
}

.st-btn:active:not(:disabled) {
  transform: scale(0.95);
}

.st-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.st-btn--play {
  width: 38px;
  height: 38px;
  font-size: 18px;
  border-color: #4F7CFF;
  color: #4F7CFF;
  background: rgba(79, 124, 255, 0.06);
}

.st-btn--play:hover:not(:disabled) {
  background: rgba(79, 124, 255, 0.14);
}

/* Progress */
.st-controls__center {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 120px;
}

.st-progress-label {
  font-size: 11px;
  color: #A8A6A2;
  font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace;
  min-width: 28px;
  text-align: center;
  user-select: none;
}

.st-progress-track {
  flex: 1;
  position: relative;
  height: 5px;
  border-radius: 3px;
  overflow: hidden;
  background: #F0EFEC;
}

.st-progress-phase {
  position: absolute;
  top: 0;
  height: 100%;
}

.st-progress-slider {
  position: absolute;
  inset: -4px 0;
  width: 100%;
  opacity: 0;
  cursor: pointer;
  margin: 0;
  z-index: 2;
}

.st-progress-slider:disabled {
  cursor: not-allowed;
}

.st-progress-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: linear-gradient(90deg,
    hsl(30, 90%, 55%),
    hsl(225, 100%, 55%) 35%,
    hsl(285, 100%, 60%) 75%,
    hsl(340, 100%, 58%) 100%
  );
  border-radius: 3px;
  pointer-events: none;
  z-index: 1;
  transition: width 150ms linear;
}

/* Speed & View */
.st-controls__right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.st-speed-icon {
  color: #A8A6A2;
  font-size: 14px;
  display: flex;
}

.st-speed-group {
  display: flex;
  gap: 2px;
  background: #F5F4F2;
  border-radius: 8px;
  padding: 2px;
}

.st-speed-btn {
  padding: 3px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #82807C;
  font-size: 12px;
  font-weight: 500;
  font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace;
  cursor: pointer;
  transition: background 150ms, color 150ms;
}

.st-speed-btn:hover {
  color: #3D3B39;
  background: rgba(255, 255, 255, 0.5);
}

.st-speed-btn--active {
  background: #fff;
  color: #4F7CFF;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.st-view-toggle {
  display: flex;
  gap: 0;
  background: #F5F4F2;
  border-radius: 8px;
  padding: 2px;
  margin-left: 4px;
}

.st-view-btn {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 4px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #82807C;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 150ms, color 150ms;
}

.st-view-btn:hover {
  color: #3D3B39;
  background: rgba(255, 255, 255, 0.5);
}

.st-view-btn--active {
  background: #fff;
  color: #4F7CFF;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

/* ═══════════ Legend ═══════════ */
.st-legend {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px 16px;
  padding: 0 20px 14px;
  flex-wrap: wrap;
}

.st-legend__phase {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #82807C;
}

.legend-swatch {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}

.st-legend__divider {
  width: 1px;
  height: 12px;
  background: #E8E0D8;
}

.st-legend__stat {
  font-size: 11px;
  color: #A8A6A2;
  font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace;
}

/* ═══════════ Responsive ═══════════ */
@media (max-width: 768px) {
  .phase-indicator {
    flex-wrap: wrap;
  }

  .phase-segment {
    padding: 4px 8px;
    gap: 4px;
  }

  .phase-segment__label {
    font-size: 11px;
  }

  .phase-connector {
    width: 12px;
  }

  .phase-desc {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }

  .st-controls {
    flex-wrap: wrap;
    gap: 10px;
    padding: 10px 14px 12px;
  }

  .st-controls__center {
    order: -1;
    width: 100%;
  }

  .st-controls__right {
    width: 100%;
    justify-content: flex-end;
  }
}

@media (max-width: 480px) {
  .phase-segment {
    padding: 3px 6px;
  }

  .phase-segment__label {
    display: none;
  }

  .st-speed-group {
    display: none; /* 小屏隐藏速度档位 */
  }

  .st-view-toggle {
    margin-left: 0;
  }
}
</style>
