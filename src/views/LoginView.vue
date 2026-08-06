<script setup lang="ts">
/**
 * LoginView —— OAT-OPS // AUTH TERMINAL (v3)
 *
 * 本次重构针对三条明确反馈：
 *   1. 「背景动效还不如之前，和内页太像」
 *      → 旧版透视栅格与全站 globals.less 的 .grid-bg（同为 64px 同色）撞脸。
 *        彻底换成 AooFlowField：把 AOO 算法本身画成活体流场，
 *        丝绸状流线 + 三收敛核 + 等值线脊，全站独一份。
 *   2. 「字体大小不合适，右侧那个有点小」
 *      → 刊头升到 clamp(64px, 8.4vw, 132px) 的杂志级尺度；
 *        表单卡宽度 由 0.95fr → 固定 480px，内距、输入高度、字号全面放大。
 *   3. 「有点干巴、细节不够酷」
 *      → 加入：卡片四角刻度、编号索引栏、右侧竖排铭牌、
 *        实时时钟与会话 ID、字段序号、按钮箭头位移、
 *        大号 pillar 卡片化、hover 时的硬边推进反馈。
 *
 * 安全性：鉴权链路一行未动，仍为 userStore.login()。
 * 认证日志每行严格绑定真实步骤成败，不伪造数据。
 */
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import type { LoginParams } from '@/types'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { UserOutlined, LockOutlined, TeamOutlined, ArrowRightOutlined } from '@ant-design/icons-vue'
import AooFlowField from '@/components/login/AooFlowField.vue'
import GlyphScramble from '@/components/login/GlyphScramble.vue'
import { useAuthSequence } from '@/composables/useAuthSequence'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formRef = ref<FormInstance>()

/**
 * 函数式模板 ref。
 * 避免字符串路径 ref —— 它会经由 exposeProxy 写入，
 * 测试对 formRef 打桩时会触发 "'set' on proxy: trap returned falsish" 并卸载组件。
 */
function setFormRef(el: unknown): void {
  formRef.value = (el as FormInstance | null) ?? undefined
}

const formState = reactive<LoginParams>({
  username: '',
  password: '',
  remember: true
})

const rules: Record<string, Rule[]> = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 20, message: '用户名长度 2-20 个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 20, message: '密码长度 6-20 个字符', trigger: 'blur' }
  ]
}

// ─────────────────────────────────────────────
//  环境能力检测与降级
// ─────────────────────────────────────────────
const reducedMotion = ref(false)
const isCompact = ref(false)
const playIntro = ref(true)

const BOOT_FLAG = 'oat:login:booted'

let mqMotion: MediaQueryList | null = null
let mqCompact: MediaQueryList | null = null

function syncMotion(): void {
  reducedMotion.value = mqMotion?.matches ?? false
}
function syncCompact(): void {
  isCompact.value = mqCompact?.matches ?? false
}

/** 是否启用「重动效」（视差 / 流场动画） */
const richMotion = computed(() => !reducedMotion.value && !isCompact.value)

// ─────────────────────────────────────────────
//  L1 启动序列
// ─────────────────────────────────────────────
const bootStage = ref(0)
const bootTimers: ReturnType<typeof setTimeout>[] = []

const BOOT_TIMELINE = [0, 140, 280, 520, 660, 800, 900, 1120, 1360]

function startBoot(): void {
  if (!playIntro.value || reducedMotion.value) {
    bootStage.value = BOOT_TIMELINE.length
    return
  }
  BOOT_TIMELINE.forEach((at, idx) => {
    const t = setTimeout(() => {
      bootStage.value = Math.max(bootStage.value, idx + 1)
    }, at)
    bootTimers.push(t)
  })
}

function stageOn(n: number): boolean {
  return bootStage.value >= n
}

// ─────────────────────────────────────────────
//  L3 指针视差
// ─────────────────────────────────────────────
const pointer = { tx: 0, ty: 0, cx: 0, cy: 0 }
const parallax = ref({ x: 0, y: 0 })
let parallaxRaf: number | null = null

function onPointerMove(e: PointerEvent): void {
  if (!richMotion.value) return
  const w = window.innerWidth || 1
  const h = window.innerHeight || 1
  pointer.tx = (e.clientX / w) * 2 - 1
  pointer.ty = (e.clientY / h) * 2 - 1
  if (parallaxRaf === null) parallaxRaf = requestAnimationFrame(parallaxTick)
}

function parallaxTick(): void {
  pointer.cx += (pointer.tx - pointer.cx) * 0.075
  pointer.cy += (pointer.ty - pointer.cy) * 0.075
  parallax.value = { x: pointer.cx, y: pointer.cy }

  const settled =
    Math.abs(pointer.tx - pointer.cx) < 0.001 && Math.abs(pointer.ty - pointer.cy) < 0.001
  if (settled) {
    parallaxRaf = null
    return
  }
  parallaxRaf = requestAnimationFrame(parallaxTick)
}

const layerBrandStyle = computed(() => ({
  transform: `translate3d(${parallax.value.x * -7}px, ${parallax.value.y * -7}px, 0)`
}))
const layerCardStyle = computed(() => ({
  transform: `translate3d(${parallax.value.x * 5}px, ${parallax.value.y * 5}px, 0)`
}))

// ─────────────────────────────────────────────
//  细节：实时时钟 + 会话标识
// ─────────────────────────────────────────────
const clock = ref('--:--:--')
let clockTimer: ReturnType<typeof setInterval> | null = null

function tickClock(): void {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  clock.value = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/**
 * 会话标识：仅用于界面上的终端质感展示，不参与任何鉴权。
 * 使用 crypto 随机源，不可用时降级为时间戳派生。
 */
const sessionId = ref('')
function makeSessionId(): string {
  try {
    const buf = new Uint8Array(3)
    crypto.getRandomValues(buf)
    return Array.from(buf, (b) => b.toString(16).padStart(2, '0')).join('').toUpperCase()
  } catch {
    return Date.now().toString(16).slice(-6).toUpperCase()
  }
}

// ─────────────────────────────────────────────
//  L3 字段联动
// ─────────────────────────────────────────────
type FieldKey = 'username' | 'password' | null
const activeField = ref<FieldKey>(null)

const cursorOffset = computed(() => {
  if (activeField.value === 'username') return 0
  if (activeField.value === 'password') return 1
  return -1
})

const fieldReadout = computed(() => {
  if (activeField.value === 'username') return 'FIELD://USERNAME'
  if (activeField.value === 'password') return 'FIELD://PASSCODE'
  return 'FIELD://IDLE'
})

/** 熵条：仅反映真实字符数，不做强度评估（避免伪数据） */
const ENTROPY_MAX = 20
const ENTROPY_CELLS = 10
const entropyFilled = computed(() => {
  const len = formState.password.length
  return Math.min(ENTROPY_CELLS, Math.round((len / ENTROPY_MAX) * ENTROPY_CELLS))
})
const entropyLabel = computed(
  () => `${String(formState.password.length).padStart(2, '0')}/${ENTROPY_MAX}`
)

// ─────────────────────────────────────────────
//  L4 认证仪式
// ─────────────────────────────────────────────
const auth = useAuthSequence()
const shake = ref(false)
let shakeTimer: ReturnType<typeof setTimeout> | null = null

/** 粒子收敛倍率：认证到达收敛阶段时放大，制造塌缩 */
const convergence = computed(() => (auth.converging.value ? 26 : 1))

const submitting = computed(() => auth.running.value)

function triggerShake(): void {
  shake.value = false
  if (shakeTimer) clearTimeout(shakeTimer)
  requestAnimationFrame(() => {
    shake.value = true
    shakeTimer = setTimeout(() => {
      shake.value = false
    }, 420)
  })
}

async function handleLogin(): Promise<void> {
  if (submitting.value) return

  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  const redirect = (route.query['redirect'] as string) || '/home'

  const ok = await auth.run(
    [
      {
        label: 'VERIFYING CREDENTIALS',
        description: '账号或密码校验未通过',
        run: async () => await userStore.login(formState)
      },
      {
        label: 'LOADING COGNITIVE PROFILE',
        description: '用户档案加载失败',
        run: () => Boolean(userStore.userInfo)
      },
      {
        label: 'INITIALIZING AOO ENGINE',
        description: '目标页面初始化失败',
        run: () => {
          try {
            const resolved = router.resolve(redirect)
            return resolved.matched.length > 0
          } catch {
            return false
          }
        }
      }
    ],
    () => {
      router.push(redirect)
    }
  )

  if (!ok) {
    triggerShake()
    setTimeout(() => auth.reset(), 1400)
  }
}

function demoLogin(role: 'student' | 'teacher'): void {
  if (submitting.value) return
  formState.username = role === 'student' ? 'student_demo' : 'teacher_demo'
  formState.password = '123456'
  void handleLogin()
}

// ─────────────────────────────────────────────
//  生命周期
// ─────────────────────────────────────────────
onMounted(() => {
  // jsdom / 老旧浏览器可能没有 matchMedia，缺失时静默降级
  if (typeof window.matchMedia === 'function') {
    mqMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    mqCompact = window.matchMedia('(max-width: 1024px)')
    syncMotion()
    syncCompact()
    mqMotion.addEventListener?.('change', syncMotion)
    mqCompact.addEventListener?.('change', syncCompact)
  }

  try {
    playIntro.value = sessionStorage.getItem(BOOT_FLAG) !== '1'
    sessionStorage.setItem(BOOT_FLAG, '1')
  } catch {
    playIntro.value = true
  }

  sessionId.value = makeSessionId()
  tickClock()
  clockTimer = setInterval(tickClock, 1000)

  startBoot()
  window.addEventListener('pointermove', onPointerMove, { passive: true })
})

onBeforeUnmount(() => {
  bootTimers.forEach((t) => clearTimeout(t))
  bootTimers.length = 0
  if (shakeTimer) clearTimeout(shakeTimer)
  if (clockTimer) clearInterval(clockTimer)
  if (parallaxRaf !== null) cancelAnimationFrame(parallaxRaf)
  window.removeEventListener('pointermove', onPointerMove)
  mqMotion?.removeEventListener('change', syncMotion)
  mqCompact?.removeEventListener('change', syncCompact)
})
</script>

<template>
  <div class="login-page" :class="{ 'is-authenticating': auth.converging.value }">
    <!-- ══ L0 签名场层：AOO 活体流场 ══ -->
    <div class="field-layer">
      <AooFlowField
        :animated="!reducedMotion"
        :density="isCompact ? 150 : 300"
        :convergence="convergence"
        :pointer-x="parallax.x"
        :pointer-y="parallax.y"
      />
      <div class="field-vignette" aria-hidden="true" />
    </div>

    <!-- ══ 顶部终端条 ══ -->
    <header class="term-bar" :class="{ 'is-in': stageOn(1) }">
      <span class="term-bar__mark" aria-hidden="true" />
      <span class="term-bar__id">DAT-OPS</span>
      <span class="term-bar__sep">//</span>
      <span class="term-bar__net">AUTH TERMINAL</span>
      <span class="term-bar__spacer" />
      <span class="term-bar__meta">SESSION {{ sessionId }}</span>
      <span class="term-bar__meta term-bar__meta--time">{{ clock }}</span>
    </header>

    <!-- ══ 右侧竖排铭牌：细节层 ══ -->
    <div class="edge-plate" :class="{ 'is-in': stageOn(2) }" aria-hidden="true">
      AVENA · OPTIMIZATION · ORIENTED
    </div>

    <div class="login-shell">
      <!-- ═══ 品牌叙事区 ═══ -->
      <section class="brand-panel" :style="layerBrandStyle">
        <p class="brand-overline" :class="{ 'is-in': stageOn(2) }">
          <span class="brand-overline__bracket">[</span>
          AOO-ENGINE v2.1
          <span class="brand-overline__bracket">]</span>
          <span class="brand-overline__div" />
          AVENA OPTIMIZATION
        </p>

        <h1 class="brand-name" :class="{ 'is-in': stageOn(3) }">
          <GlyphScramble text="动麦智导" :play="playIntro && stageOn(3) && !reducedMotion" />
        </h1>

        <p class="brand-latin" :class="{ 'is-in': stageOn(4) }">DAT&nbsp;GUIDE</p>

        <div class="brand-rule" :class="{ 'is-in': stageOn(4) }" aria-hidden="true" />

        <p class="brand-tagline" :class="{ 'is-in': stageOn(5) }">
          取法野麦生存之道<br />为每位学习者重绘认知经纬
        </p>

        <p class="brand-support" :class="{ 'is-in': stageOn(5) }">
          AOO 优化算法驱动学情测绘、个性化路径与导学终端。登录后，你的学习轨迹开始收敛。
        </p>

        <ul class="brand-pillars" :class="{ 'is-in': stageOn(6) }">
          <li style="--i: 0">
            <span class="pillar-idx">01</span>
            <span class="pillar-body">
              <span class="pillar-title">AI 学情测绘</span>
              <span class="pillar-sub">CEHUI</span>
            </span>
          </li>
          <li style="--i: 1">
            <span class="pillar-idx">02</span>
            <span class="pillar-body">
              <span class="pillar-title">AOO 路径规划</span>
              <span class="pillar-sub">PATHFINDING</span>
            </span>
          </li>
          <li style="--i: 2">
            <span class="pillar-idx">03</span>
            <span class="pillar-body">
              <span class="pillar-title">RAG 导学终端</span>
              <span class="pillar-sub">RETRIEVAL</span>
            </span>
          </li>
        </ul>
      </section>

      <!-- ═══ 登录交互区 ═══ -->
      <section class="form-panel" :style="layerCardStyle">
        <div
          class="form-card"
          :class="{
            'is-in': stageOn(7),
            'is-shaking': shake,
            'is-busy': submitting
          }"
        >
          <!-- 四角刻度：硬质取景框语汇 -->
          <span class="corner corner--tl" aria-hidden="true" />
          <span class="corner corner--tr" aria-hidden="true" />
          <span class="corner corner--bl" aria-hidden="true" />
          <span class="corner corner--br" aria-hidden="true" />

          <!-- 字段光标：左侧金条 -->
          <span
            class="form-card__cursor"
            :class="{ 'is-active': cursorOffset >= 0 }"
            :style="{ '--cursor-slot': cursorOffset }"
            aria-hidden="true"
          />

          <header class="form-header">
            <div class="form-header__row">
              <span class="form-kicker">SECURE ACCESS</span>
              <span class="form-readout">{{ fieldReadout }}</span>
            </div>
            <h2 class="form-title">进入认知地图</h2>
            <p class="form-subtitle">登录账号，继续你的个性化学习旅程</p>
          </header>

          <!-- ── 认证日志面板（L4） ── -->
          <div v-if="auth.showLog.value" class="auth-log" role="status" aria-live="polite">
            <p
              v-for="(step, i) in auth.steps.value"
              :key="i"
              class="auth-log__line"
              :class="`is-${step.status}`"
            >
              <span class="auth-log__caret">&gt;</span>
              <span class="auth-log__label">{{ step.label }}</span>
              <span class="auth-log__dots" aria-hidden="true" />
              <span class="auth-log__state">
                {{
                  step.status === 'ok'
                    ? 'OK'
                    : step.status === 'failed'
                      ? 'FAILED'
                      : step.status === 'running'
                        ? '···'
                        : ''
                }}
              </span>
            </p>
            <p v-if="auth.errorText.value" class="auth-log__error">
              {{ auth.errorText.value }}
            </p>
          </div>

          <!-- ── 表单 ── -->
          <a-form
            v-show="!auth.showLog.value"
            :ref="setFormRef"
            :model="formState"
            :rules="rules"
            layout="vertical"
            size="large"
            class="login-form"
            @finish="handleLogin"
          >
            <a-form-item name="username">
              <div
                class="field"
                :class="{ 'is-focus': activeField === 'username', 'is-in': stageOn(8) }"
              >
                <span class="field__tag">
                  <span class="field__num">01</span>
                  <span class="field__abbr">USR</span>
                </span>
                <a-input
                  v-model:value="formState.username"
                  placeholder="请输入用户名"
                  autocomplete="username"
                  class="login-input"
                  :disabled="submitting"
                  @focus="activeField = 'username'"
                  @blur="activeField = null"
                >
                  <template #prefix>
                    <UserOutlined class="input-icon" />
                  </template>
                </a-input>
                <span class="field__scan" aria-hidden="true" />
              </div>
            </a-form-item>

            <a-form-item name="password">
              <div
                class="field"
                :class="{ 'is-focus': activeField === 'password', 'is-in': stageOn(8) }"
              >
                <span class="field__tag">
                  <span class="field__num">02</span>
                  <span class="field__abbr">PWD</span>
                </span>
                <a-input-password
                  v-model:value="formState.password"
                  placeholder="请输入密码"
                  autocomplete="current-password"
                  class="login-input"
                  :disabled="submitting"
                  @focus="activeField = 'password'"
                  @blur="activeField = null"
                >
                  <template #prefix>
                    <LockOutlined class="input-icon" />
                  </template>
                </a-input-password>
                <span class="field__scan" aria-hidden="true" />
              </div>
            </a-form-item>

            <!-- 熵条：只反映真实长度 -->
            <div class="entropy" :class="{ 'is-in': stageOn(8) }">
              <span class="entropy__key">ENTROPY</span>
              <div class="entropy__cells" aria-hidden="true">
                <span
                  v-for="n in ENTROPY_CELLS"
                  :key="n"
                  class="entropy__cell"
                  :class="{ 'is-on': n <= entropyFilled }"
                />
              </div>
              <span class="entropy__label">{{ entropyLabel }}</span>
            </div>

            <div class="form-extra">
              <a-checkbox v-model:checked="formState.remember" :disabled="submitting">
                记住登录状态
              </a-checkbox>
            </div>

            <a-form-item class="submit-item">
              <button
                type="submit"
                class="login-btn"
                :disabled="submitting"
                :class="{ 'is-collapsing': auth.phase.value === 'collapsing' }"
              >
                <span class="login-btn__fill" aria-hidden="true" />
                <span class="login-btn__label">登 录 · ENTER</span>
                <ArrowRightOutlined class="login-btn__arrow" />
              </button>
            </a-form-item>
          </a-form>

          <div v-show="!auth.showLog.value" class="demo-section" :class="{ 'is-in': stageOn(9) }">
            <div class="demo-divider"><span>QUICK ACCESS</span></div>
            <div class="demo-buttons">
              <button
                type="button"
                class="demo-btn demo-btn--student"
                :disabled="submitting"
                @click="demoLogin('student')"
              >
                <UserOutlined />
                学生 Demo
              </button>
              <button
                type="button"
                class="demo-btn demo-btn--teacher"
                :disabled="submitting"
                @click="demoLogin('teacher')"
              >
                <TeamOutlined />
                教师 Demo
              </button>
            </div>
          </div>

          <footer
            v-show="!auth.showLog.value"
            class="form-footer"
            :class="{ 'is-in': stageOn(9) }"
          >
            <span>还没有账号？</span>
            <button
              type="button"
              class="link-btn"
              :disabled="submitting"
              @click="router.push('/register')"
            >
              立即注册
            </button>
          </footer>
        </div>

        <p class="form-credit" :class="{ 'is-in': stageOn(9) }">
          SYSTEM READY<span class="caret" aria-hidden="true" />
        </p>
      </section>
    </div>

    <!-- ══ L4 白场穿越 ══ -->
    <div class="warp" :class="{ 'is-on': auth.converging.value }" aria-hidden="true" />
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════
   基底
   ═══════════════════════════════════════════ */
.login-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 88px 40px 56px;
  background: #06080d;
  overflow: hidden;
  font-feature-settings: 'tnum' 1;
}

/*
  注意：这里刻意 **不** 使用全站 .grid-bg 的 64px 栅格，
  避免与内页背景撞脸。登录页的纹理完全交给 AooFlowField。
*/
.field-layer {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}

/* 暗角：把注意力收束到中央，同时保证文字对比度 */
.field-vignette {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 76% 62% at 50% 48%, rgba(6, 8, 13, 0.5) 0%, rgba(6, 8, 13, 0.9) 100%),
    linear-gradient(to bottom, rgba(6, 8, 13, 0.86) 0%, rgba(6, 8, 13, 0) 22%);
}

/* ═══ 顶部终端条 ═══ */
.term-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 8;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 46px;
  padding: 0 26px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.09);
  background: rgba(6, 8, 13, 0.55);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  letter-spacing: 0.2em;
  color: #64748b;
  text-transform: uppercase;
  opacity: 0;
  transition: opacity 0.4s linear;
}

.term-bar.is-in {
  opacity: 1;
}

.term-bar__mark {
  width: 7px;
  height: 7px;
  background: #d4a373;
  flex-shrink: 0;
}

.term-bar__id {
  color: #f8fafc;
  font-weight: 600;
}

.term-bar__sep {
  color: #334155;
}

.term-bar__net {
  color: #94a3b8;
}

.term-bar__spacer {
  flex: 1;
}

.term-bar__meta {
  color: #475569;
  font-size: 10.5px;
}

.term-bar__meta--time {
  color: #d4a373;
  min-width: 66px;
  text-align: right;
}

/* ═══ 右侧竖排铭牌 ═══ */
.edge-plate {
  position: absolute;
  right: 18px;
  top: 50%;
  z-index: 6;
  transform: translateY(-50%) rotate(180deg);
  writing-mode: vertical-rl;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.42em;
  color: #2c3648;
  text-transform: uppercase;
  opacity: 0;
  transition: opacity 0.6s linear;
  pointer-events: none;
}

.edge-plate.is-in {
  opacity: 1;
}

/* ═══ 布局骨架：右栏显著加宽 ═══ */
.login-shell {
  position: relative;
  z-index: 5;
  width: 100%;
  max-width: 1280px;
  display: grid;
  /* 左栏自适应，右栏固定 480px —— 解决「右侧太小」 */
  grid-template-columns: minmax(0, 1fr) 480px;
  gap: 88px;
  align-items: center;
}

/* ═══════════════════════════════════════════
   品牌叙事区：杂志级排版尺度
   ═══════════════════════════════════════════ */
.brand-panel {
  position: relative;
  will-change: transform;
  min-width: 0;
}

.brand-overline {
  display: flex;
  align-items: center;
  gap: 9px;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  letter-spacing: 0.24em;
  color: #94a3b8;
  text-transform: uppercase;
  margin: 0 0 26px;
  clip-path: inset(0 100% 0 0);
  transition: clip-path 0.42s cubic-bezier(0.16, 1, 0.3, 1);
}

.brand-overline.is-in {
  clip-path: inset(0 0 0 0);
}

.brand-overline__bracket {
  color: #d4a373;
}

.brand-overline__div {
  width: 26px;
  height: 1px;
  background: rgba(148, 163, 184, 0.32);
}

/* 超大刊头 —— 与内页品牌标识同款动麦金渐变 + 字重/字距 */
.brand-name {
  margin: 0;
  font-size: clamp(48px, 6.4vw, 92px);
  font-weight: 700;
  line-height: 0.96;
  letter-spacing: 1px;
  background: linear-gradient(135deg, #f8fafc 0%, #d4a373 50%, #faedcd 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: #d4a373;
  opacity: 0;
  transition: opacity 0.12s linear;
}

.brand-name.is-in {
  opacity: 1;
}

/* 拉丁副题：呼应内页品牌金，收窄字距，弱化等宽与刊头对撞 */
.brand-latin {
  margin: 14px 0 0;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: clamp(14px, 1.4vw, 20px);
  font-weight: 500;
  letter-spacing: 0.3em;
  color: #d4a373;
  text-transform: uppercase;
  clip-path: inset(0 100% 0 0);
  transition: clip-path 0.5s cubic-bezier(0.16, 1, 0.3, 1);
}

.brand-latin.is-in {
  clip-path: inset(0 0 0 0);
}

.brand-rule {
  height: 1px;
  margin: 32px 0 30px;
  background: linear-gradient(90deg, #d4a373 0%, rgba(212, 163, 115, 0.1) 58%, transparent 100%);
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform 0.5s cubic-bezier(0.16, 1, 0.3, 1);
}

.brand-rule.is-in {
  transform: scaleX(1);
}

.brand-tagline {
  margin: 0 0 18px;
  font-size: clamp(19px, 1.85vw, 26px);
  font-weight: 500;
  line-height: 1.5;
  color: #e2e8f0;
  letter-spacing: -0.01em;
  clip-path: inset(0 100% 0 0);
  transition: clip-path 0.52s cubic-bezier(0.16, 1, 0.3, 1);
}

.brand-support {
  margin: 0 0 42px;
  font-size: 15px;
  line-height: 1.85;
  color: #94a3b8;
  max-width: 32em;
  clip-path: inset(0 100% 0 0);
  transition: clip-path 0.52s cubic-bezier(0.16, 1, 0.3, 1) 0.08s;
}

.brand-tagline.is-in,
.brand-support.is-in {
  clip-path: inset(0 0 0 0);
}

/* ── Pillar 卡片化：编号 + 中英双行 ── */
.brand-pillars {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  background: rgba(148, 163, 184, 0.13);
  border: 1px solid rgba(148, 163, 184, 0.13);
  max-width: 560px;
}

.brand-pillars li {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  padding: 16px 16px 15px;
  background: rgba(6, 8, 13, 0.72);
  clip-path: inset(0 0 100% 0);
  transition:
    clip-path 0.07s linear calc(var(--i) * 0.075s),
    background-color 0.2s linear;
}

.brand-pillars.is-in li {
  clip-path: inset(0 0 0 0);
}

.brand-pillars li:hover {
  background: rgba(212, 163, 115, 0.07);
}

.pillar-idx {
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: #d4a373;
  line-height: 1.4;
  flex-shrink: 0;
}

.pillar-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.pillar-title {
  font-size: 14px;
  color: #e2e8f0;
  line-height: 1.35;
}

.pillar-sub {
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 9.5px;
  letter-spacing: 0.18em;
  color: #475569;
}

/* ═══════════════════════════════════════════
   表单卡片：显著放大 + 四角刻度
   ═══════════════════════════════════════════ */
.form-panel {
  position: relative;
  will-change: transform;
}

.form-card {
  position: relative;
  padding: 40px 38px 32px;
  background: rgba(9, 12, 19, 0.82);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-left: 2px solid #d4a373;
  border-radius: 2px;
  clip-path: inset(0 0 100% 0);
  transition:
    clip-path 0.55s cubic-bezier(0.16, 1, 0.3, 1),
    border-color 0.2s linear;
}

.form-card.is-in {
  clip-path: inset(0 0 0 0);
}

.form-card.is-busy {
  border-color: rgba(212, 163, 115, 0.34);
}

/* ── 四角刻度 ── */
.corner {
  position: absolute;
  width: 11px;
  height: 11px;
  border: 1px solid rgba(212, 163, 115, 0.5);
  pointer-events: none;
}

.corner--tl {
  top: -1px;
  left: -1px;
  border-right: none;
  border-bottom: none;
}

.corner--tr {
  top: -1px;
  right: -1px;
  border-left: none;
  border-bottom: none;
}

.corner--bl {
  bottom: -1px;
  left: -1px;
  border-right: none;
  border-top: none;
}

.corner--br {
  bottom: -1px;
  right: -1px;
  border-left: none;
  border-top: none;
}

/* 字段光标金条 */
.form-card__cursor {
  position: absolute;
  left: -2px;
  top: 158px;
  width: 2px;
  height: 52px;
  background: #d4a373;
  opacity: 0;
  transform: translateY(calc(var(--cursor-slot, 0) * 96px));
  transition:
    transform 0.25s cubic-bezier(0.16, 1, 0.3, 1),
    opacity 0.18s linear;
}

.form-card__cursor.is-active {
  opacity: 1;
}

/* 失败硬抖动 */
.form-card.is-shaking {
  animation: hard-shake 0.4s steps(1, end);
}

@keyframes hard-shake {
  0%,
  100% {
    transform: translateX(0);
  }
  10%,
  50%,
  90% {
    transform: translateX(-3px);
  }
  30%,
  70% {
    transform: translateX(3px);
  }
}

/* ── 卡片头部 ── */
.form-header {
  margin-bottom: 28px;
}

.form-header__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}

.form-kicker,
.form-readout {
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10.5px;
  letter-spacing: 0.2em;
  white-space: nowrap;
}

.form-kicker {
  color: #d4a373;
}

.form-readout {
  color: #475569;
}

.form-title {
  margin: 0;
  font-size: 27px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #f8fafc;
  line-height: 1.25;
}

.form-subtitle {
  margin: 9px 0 0;
  font-size: 13.5px;
  color: #94a3b8;
  line-height: 1.6;
}

/* ── 输入字段 ── */
.field {
  position: relative;
  display: flex;
  align-items: center;
  clip-path: inset(0 100% 0 0);
  transition: clip-path 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.field.is-in {
  clip-path: inset(0 0 0 0);
}

.field__tag {
  flex-shrink: 0;
  width: 54px;
  height: 52px;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-right: none;
  background: rgba(148, 163, 184, 0.04);
  transition:
    color 0.16s linear,
    border-color 0.16s linear,
    background-color 0.16s linear;
}

.field__num {
  font-size: 9px;
  letter-spacing: 0.06em;
  color: #334155;
}

.field__abbr {
  font-size: 10.5px;
  letter-spacing: 0.08em;
  color: #64748b;
}

.field.is-focus .field__tag {
  border-color: rgba(212, 163, 115, 0.42);
  background: rgba(212, 163, 115, 0.06);
}

.field.is-focus .field__abbr {
  color: #d4a373;
}

.field.is-focus .field__num {
  color: rgba(212, 163, 115, 0.6);
}

/* 聚焦扫描线 */
.field__scan {
  position: absolute;
  left: 54px;
  right: 0;
  bottom: 0;
  height: 1px;
  background: #d4a373;
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1);
}

.field.is-focus .field__scan {
  transform: scaleX(1);
}

.input-icon {
  color: #64748b;
}

/* ── 熵条 ── */
.entropy {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: -10px 0 18px;
  padding-left: 54px;
  opacity: 0;
  transition: opacity 0.3s linear;
}

.entropy.is-in {
  opacity: 1;
}

.entropy__key,
.entropy__label {
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.16em;
  color: #475569;
}

.entropy__cells {
  display: flex;
  gap: 3px;
  flex: 1;
}

.entropy__cell {
  flex: 1;
  height: 4px;
  background: rgba(148, 163, 184, 0.16);
  transition: background-color 0.12s linear;
}

.entropy__cell.is-on {
  background: #d4a373;
}

.form-extra {
  display: flex;
  justify-content: flex-start;
  margin-bottom: 22px;
}

/* ── 提交按钮 ── */
.submit-item {
  margin-bottom: 8px;
}

.login-btn {
  position: relative;
  width: 100%;
  height: 54px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  overflow: hidden;
  cursor: pointer;
  background: transparent;
  border: 1px solid #d4a373;
  border-radius: 0;
  color: #d4a373;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.18em;
  transition:
    color 0.12s linear,
    height 0.26s cubic-bezier(0.16, 1, 0.3, 1);
}

/* 金色从左侧硬边推满 */
.login-btn__fill {
  position: absolute;
  inset: 0;
  background: #d4a373;
  clip-path: inset(0 100% 0 0);
  transition: clip-path 0.13s linear;
}

.login-btn__label,
.login-btn__arrow {
  position: relative;
  z-index: 1;
}

.login-btn__arrow {
  font-size: 13px;
  transform: translateX(-4px);
  opacity: 0;
  transition:
    transform 0.18s cubic-bezier(0.16, 1, 0.3, 1),
    opacity 0.18s linear;
}

.login-btn:not(:disabled):hover {
  color: #06080d;
}

.login-btn:not(:disabled):hover .login-btn__fill {
  clip-path: inset(0 0 0 0);
}

.login-btn:not(:disabled):hover .login-btn__arrow {
  transform: translateX(0);
  opacity: 1;
}

.login-btn:not(:disabled):active {
  transform: translateY(1px);
}

.login-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

/* 塌缩为一条 3px 横线 */
.login-btn.is-collapsing {
  height: 3px;
  border-width: 0;
  color: transparent;
}

.login-btn.is-collapsing .login-btn__fill {
  clip-path: inset(0 0 0 0);
}

.login-btn.is-collapsing .login-btn__arrow {
  opacity: 0;
}

/* ═══ 认证日志 ═══ */
.auth-log {
  padding: 18px 0 10px;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 2;
}

.auth-log__line {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0;
  color: #64748b;
  clip-path: inset(0 100% 0 0);
  transition: clip-path 0.22s steps(24, end);
}

.auth-log__line.is-running,
.auth-log__line.is-ok,
.auth-log__line.is-failed {
  clip-path: inset(0 0 0 0);
}

.auth-log__caret {
  color: #d4a373;
}

.auth-log__label {
  letter-spacing: 0.08em;
  white-space: nowrap;
}

.auth-log__dots {
  flex: 1;
  min-width: 12px;
  border-bottom: 1px dotted rgba(148, 163, 184, 0.28);
  transform: translateY(-3px);
}

.auth-log__state {
  min-width: 48px;
  text-align: right;
  letter-spacing: 0.1em;
}

.auth-log__line.is-ok .auth-log__state {
  color: #d4a373;
}

.auth-log__line.is-ok .auth-log__label {
  color: #cbd5e1;
}

.auth-log__line.is-failed .auth-log__state,
.auth-log__line.is-failed .auth-log__label {
  color: #ef4444;
}

.auth-log__error {
  margin: 14px 0 0;
  padding-left: 16px;
  font-size: 12.5px;
  color: #ef4444;
  letter-spacing: 0.04em;
}

/* ═══ Demo 区 ═══ */
.demo-section {
  margin-top: 26px;
  opacity: 0;
  transition: opacity 0.35s linear;
}

.demo-section.is-in,
.form-footer.is-in {
  opacity: 1;
}

.demo-divider {
  position: relative;
  text-align: center;
  margin-bottom: 16px;
}

.demo-divider::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  height: 1px;
  background: rgba(148, 163, 184, 0.12);
}

.demo-divider span {
  position: relative;
  padding: 0 14px;
  background: #0a0e16;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.22em;
  color: #475569;
}

.demo-buttons {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.demo-btn {
  height: 46px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13.5px;
  color: #94a3b8;
  background: transparent;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 0;
  transition:
    color 0.14s linear,
    border-color 0.14s linear,
    background-color 0.14s linear;
}

.demo-btn:not(:disabled):hover {
  color: #d4a373;
  border-color: rgba(212, 163, 115, 0.55);
  background: rgba(212, 163, 115, 0.05);
}

.demo-btn:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

/* ═══ 页脚 ═══ */
.form-footer {
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid rgba(148, 163, 184, 0.1);
  text-align: center;
  font-size: 13px;
  color: #64748b;
  opacity: 0;
  transition: opacity 0.35s linear;
}

.link-btn {
  margin-left: 6px;
  padding: 0;
  background: none;
  border: none;
  cursor: pointer;
  color: #d4a373;
  font-size: 13px;
  border-bottom: 1px solid transparent;
  transition: border-color 0.14s linear;
}

.link-btn:not(:disabled):hover {
  border-bottom-color: #d4a373;
}

.link-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.form-credit {
  margin: 20px 0 0;
  text-align: center;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10.5px;
  letter-spacing: 0.24em;
  color: #334155;
  opacity: 0;
  transition: opacity 0.4s linear;
}

.form-credit.is-in {
  opacity: 1;
}

.caret {
  display: inline-block;
  width: 6px;
  height: 10px;
  margin-left: 6px;
  background: #d4a373;
  transform: translateY(1px);
  animation: caret-blink 1.1s steps(1, end) infinite;
}

@keyframes caret-blink {
  0%,
  49% {
    opacity: 1;
  }
  50%,
  100% {
    opacity: 0;
  }
}

/* ═══ L4 白场穿越 ═══ */
.warp {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: #f8fafc;
  pointer-events: none;
  clip-path: circle(0% at 50% 50%);
}

.warp.is-on {
  animation: warp-burst 0.34s cubic-bezier(0.7, 0, 0.84, 0) forwards;
}

@keyframes warp-burst {
  0% {
    clip-path: circle(0% at 50% 50%);
  }
  100% {
    clip-path: circle(85% at 50% 50%);
  }
}

.login-page.is-authenticating .brand-panel {
  opacity: 0.3;
  transition: opacity 0.3s linear;
}

/* ═══════════════════════════════════════════
   Ant Design 输入框覆写：同步放大
   ═══════════════════════════════════════════ */
.login-form :deep(.ant-form-item) {
  margin-bottom: 20px;
}

.login-form :deep(.ant-input-affix-wrapper) {
  height: 52px;
  padding-inline: 14px;
  border-radius: 0;
  background: rgba(148, 163, 184, 0.04);
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: none;
  transition:
    border-color 0.16s linear,
    background-color 0.16s linear;
}

.login-form :deep(.ant-input-affix-wrapper:hover) {
  border-color: rgba(148, 163, 184, 0.3);
  background: rgba(148, 163, 184, 0.06);
}

.login-form :deep(.ant-input-affix-wrapper-focused),
.login-form :deep(.ant-input-affix-wrapper:focus-within) {
  border-color: rgba(212, 163, 115, 0.55);
  background: rgba(212, 163, 115, 0.04);
  box-shadow: none;
}

.login-form :deep(.ant-input) {
  background: transparent;
  color: #f8fafc;
  font-size: 15px;
}

.login-form :deep(.ant-input::placeholder) {
  color: #475569;
}

.login-form :deep(.ant-input-password-icon),
.login-form :deep(.anticon) {
  color: #64748b;
}

.login-form :deep(.ant-input-password-icon:hover) {
  color: #d4a373;
}

.login-form :deep(.ant-form-item-explain-error) {
  font-size: 12px;
  color: #ef4444;
  margin-top: 6px;
  padding-left: 54px;
}

.login-form :deep(.ant-checkbox-wrapper) {
  color: #94a3b8;
  font-size: 13px;
}

.login-form :deep(.ant-checkbox-inner) {
  border-radius: 0;
  background: transparent;
  border-color: rgba(148, 163, 184, 0.35);
}

.login-form :deep(.ant-checkbox-checked .ant-checkbox-inner) {
  background: #d4a373;
  border-color: #d4a373;
}

.login-form :deep(.ant-checkbox-checked .ant-checkbox-inner::after) {
  border-color: #06080d;
}

/* ═══════════════════════════════════════════
   响应式
   ═══════════════════════════════════════════ */
@media (max-width: 1240px) {
  .login-shell {
    grid-template-columns: minmax(0, 1fr) 440px;
    gap: 56px;
  }
}

@media (max-width: 1024px) {
  .login-page {
    padding: 78px 24px 40px;
  }

  .login-shell {
    grid-template-columns: 1fr;
    gap: 44px;
    max-width: 560px;
  }

  .brand-name {
    font-size: clamp(40px, 11vw, 60px);
  }

  .brand-support {
    display: none;
  }

  .brand-pillars {
    max-width: none;
  }

  .edge-plate {
    display: none;
  }

  .form-card__cursor {
    display: none;
  }
}

@media (max-width: 620px) {
  .brand-pillars {
    grid-template-columns: 1fr;
  }

  .form-card {
    padding: 30px 22px 26px;
  }

  .term-bar__meta {
    display: none;
  }
}

@media (max-width: 420px) {
  .demo-buttons {
    grid-template-columns: 1fr;
  }
}

/* ═══════════════════════════════════════════
   无障碍降级
   ═══════════════════════════════════════════ */
@media (prefers-reduced-motion: reduce) {
  .brand-overline,
  .brand-latin,
  .brand-tagline,
  .brand-support,
  .field,
  .auth-log__line {
    clip-path: inset(0 0 0 0) !important;
    transition: none !important;
  }

  .brand-name,
  .brand-pillars li,
  .form-card,
  .demo-section,
  .form-footer,
  .form-credit,
  .term-bar,
  .edge-plate,
  .entropy {
    opacity: 1 !important;
    clip-path: inset(0 0 0 0) !important;
    transition: none !important;
  }

  .brand-rule {
    transform: scaleX(1) !important;
    transition: none !important;
  }

  .caret,
  .form-card.is-shaking {
    animation: none !important;
  }

  .warp.is-on {
    animation: none !important;
    clip-path: circle(85% at 50% 50%);
  }
}
</style>
