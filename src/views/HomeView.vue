<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import {
  RocketOutlined,
  ThunderboltOutlined,
  ExperimentOutlined,
  NodeIndexOutlined,
  RobotOutlined,
  ArrowRightOutlined,
  CheckCircleOutlined,
  TeamOutlined,
  TrophyOutlined,
  EnvironmentOutlined,
  MailOutlined,
  GithubOutlined,
  GlobalOutlined,
  BulbOutlined
} from '@ant-design/icons-vue'
import { dashboardApi } from '@/api/modules/dashboard'
import OatSwayBackground from '@/components/OatSwayBackground.vue'

// ============================================================
//   Store & Router
// ============================================================
const router = useRouter()
const userStore = useUserStore()

// ============================================================
//   滚动动画 (IntersectionObserver)
// ============================================================

/** 可见性记录：section key → 是否已触发 */
const revealed = ref<Record<string, boolean>>({})
const observer = ref<IntersectionObserver | null>(null)

const SECTION_KEYS = ['features', 'algorithm', 'advantages', 'stats'] as const

function initScrollObserver() {
  observer.value = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const key = entry.target.getAttribute('data-reveal-key')
          if (key && !revealed.value[key]) {
            revealed.value = { ...revealed.value, [key]: true }

            // 统计 section 出现时，触发数字动效
            if (key === 'stats') {
              startCountUp()
            }
          }
        }
      })
    },
    { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
  )

  nextTick(() => {
    SECTION_KEYS.forEach((key) => observeSection(key))
  })
}

/** 观察单个 section（供延迟渲染的区块补注册，如统计区块） */
function observeSection(key: string) {
  const el = document.querySelector(`[data-reveal-key="${key}"]`)
  if (el) observer.value?.observe(el)
}

// ============================================================
//   数字增长动画
// ============================================================

/** 当前显示数值（动画中间值） */
const displayCounts = ref({ users: 0, paths: 0, knowledgePoints: 0 })

/** 目标数值 — 来自后端真实统计，未加载完成前为 null */
const targetCounts = ref<{ users: number; paths: number; knowledgePoints: number } | null>(null)

/** 统计数据是否已成功加载（失败时隐藏该区块，不展示假数据） */
const statsLoaded = ref(false)

/** 动画时长(ms) */
const DURATION = 2000

/** 拉取平台真实统计数据 */
async function fetchPlatformStats() {
  try {
    const stats = await dashboardApi.getPlatformStats()
    targetCounts.value = {
      users: stats.studentCount ?? 0,
      paths: stats.pathCount ?? 0,
      knowledgePoints: stats.knowledgePointCount ?? 0
    }
    statsLoaded.value = true
    // 统计区块由 v-if 延迟渲染，需在 DOM 挂载后补注册滚动观察
    await nextTick()
    if (revealed.value['stats']) {
      startCountUp() // 已在视口内：数据到达后补播动画
    } else {
      observeSection('stats')
    }
  } catch (e) {
    console.warn('[Home] 平台统计数据获取失败，已隐藏统计区块', e)
    statsLoaded.value = false
  }
}

function startCountUp() {
  const target = targetCounts.value
  if (!target) return // 真实数据未就绪时不播放动画，避免滚动到编造数字

  const startTime = performance.now()
  const startVals = { ...displayCounts.value }

  function tick(now: number) {
    const elapsed = now - startTime
    const t = Math.min(elapsed / DURATION, 1)
    // ease-out quart
    const ease = 1 - Math.pow(1 - t, 4)

    displayCounts.value = {
      users: Math.round(startVals.users + (target!.users - startVals.users) * ease),
      paths: Math.round(startVals.paths + (target!.paths - startVals.paths) * ease),
      knowledgePoints: Math.round(
        startVals.knowledgePoints + (target!.knowledgePoints - startVals.knowledgePoints) * ease
      )
    }

    if (t < 1) {
      requestAnimationFrame(tick)
    }
  }

  requestAnimationFrame(tick)
}

// ============================================================
//   导航
// ============================================================
function goTo(path: string) {
  router.push(path)
}

// ============================================================
//   生命周期
// ============================================================
onMounted(() => {
  initScrollObserver()
  fetchPlatformStats()
})

onUnmounted(() => {
  observer.value?.disconnect()
})
</script>

<template>
  <div class="home-page">
    <!-- =========================================================
         1. Hero 区域
         ========================================================= -->
    <section class="hero">
      <!-- 背景装饰：流沙麦浪 + 光斑 -->
      <div class="hero-bg">
        <OatSwayBackground :density="96" :opacity="0.9" />
        <div class="hero-orb hero-orb--1" />
        <div class="hero-orb hero-orb--2" />
        <div class="hero-orb hero-orb--3" />
      </div>

      <div class="hero-inner">
        <!-- Logo + 名称 -->
        <div class="hero-brand">
          <!-- 燕麦 Logo SVG -->
          <div class="hero-logo">
            <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
              <!-- 麦粒主体 -->
              <ellipse cx="40" cy="52" rx="12" ry="18" fill="url(#oatGrad)" opacity="0.95" />
              <!-- 麦粒高光 -->
              <ellipse cx="37" cy="47" rx="5" ry="8" fill="white" opacity="0.2" />
              <!-- 芒 (awns) -->
              <path
                d="M40 34 L34 12"
                stroke="url(#awnGrad)"
                stroke-width="2"
                stroke-linecap="round"
              />
              <path
                d="M40 34 L46 10"
                stroke="url(#awnGrad)"
                stroke-width="2"
                stroke-linecap="round"
              />
              <path
                d="M40 34 L40 8"
                stroke="url(#awnGrad)"
                stroke-width="2"
                stroke-linecap="round"
              />
              <!-- 叶 -->
              <path
                d="M32 55 Q18 48 10 56"
                stroke="url(#leafGrad)"
                stroke-width="2.5"
                fill="none"
                stroke-linecap="round"
              />
              <path
                d="M48 55 Q62 48 70 56"
                stroke="url(#leafGrad)"
                stroke-width="2.5"
                fill="none"
                stroke-linecap="round"
              />
              <!-- 外环 -->
              <circle
                cx="40"
                cy="40"
                r="36"
                stroke="url(#ringGrad)"
                stroke-width="1.5"
                fill="none"
                opacity="0.5"
              />
              <defs>
                <linearGradient
                  id="oatGrad"
                  x1="28"
                  y1="34"
                  x2="52"
                  y2="70"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#D4C08C" />
                  <stop offset="0.5" stop-color="#C4A862" />
                  <stop offset="1" stop-color="#A88B3E" />
                </linearGradient>
                <linearGradient
                  id="awnGrad"
                  x1="40"
                  y1="34"
                  x2="40"
                  y2="8"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#C4A862" />
                  <stop offset="1" stop-color="#8B6914" />
                </linearGradient>
                <linearGradient
                  id="leafGrad"
                  x1="10"
                  y1="56"
                  x2="70"
                  y2="56"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#7BA05B" />
                  <stop offset="1" stop-color="#5D8A3C" />
                </linearGradient>
                <linearGradient
                  id="ringGrad"
                  x1="4"
                  y1="4"
                  x2="76"
                  y2="76"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#4F7CFF" />
                  <stop offset="1" stop-color="#9254DE" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h1 class="hero-name">燕麦智导</h1>
        </div>

        <!-- 标语 -->
        <p class="hero-tagline">让野燕麦的生存智慧，重塑每一个学习者的认知地图</p>

        <!-- 副标题 -->
        <p class="hero-subtitle">
          基于 AOO (Animated Oat Optimization) 算法与 RAG 检索增强生成技术， 为每位学习者提供<span
            class="text-accent"
            >认知诊断</span
          >、 <span class="text-accent">个性化学习路径</span>与<span class="text-accent"
            >智能问答</span
          >的全链路学习优化
        </p>

        <!-- CTA 按钮 -->
        <div class="hero-actions">
          <a-button
            type="primary"
            size="large"
            class="hero-btn hero-btn--primary"
            @click="goTo(userStore.isTeacher ? '/teacher' : '/diagnose')"
          >
            <RocketOutlined />
            {{ userStore.isTeacher ? '进入仪表盘' : '开始诊断' }}
          </a-button>
          <a-button
            v-if="userStore.isTeacher"
            size="large"
            class="hero-btn hero-btn--ghost"
            @click="goTo('/teacher/knowledge')"
          >
            <ThunderboltOutlined />
            知识点管理
          </a-button>
          <a-button v-else size="large" class="hero-btn hero-btn--ghost" @click="goTo('/chat')">
            <ThunderboltOutlined />
            智能问答
          </a-button>
        </div>
      </div>

      <!-- 底部滚动提示 -->
      <div class="hero-scroll-hint">
        <span class="scroll-dot" />
      </div>
    </section>

    <!-- =========================================================
         2. 核心功能卡片
         ========================================================= -->
    <section
      class="section features-section"
      data-reveal-key="features"
      :class="{ 'is-revealed': revealed['features'] }"
    >
      <div class="section-header">
        <h2 class="section-title">核心功能</h2>
        <p class="section-desc">三大引擎驱动，构建完整的智能学习闭环</p>
      </div>

      <div class="features-grid">
        <!-- 认知诊断 -->
        <div class="feature-card">
          <div
            class="feature-card-icon"
            style="
              background: linear-gradient(
                135deg,
                rgba(74, 108, 247, 0.2),
                rgba(74, 108, 247, 0.08)
              );
              color: #4a6cf7;
            "
          >
            <ExperimentOutlined />
          </div>
          <h3>认知诊断</h3>
          <p>基于知识图谱的智能诊断系统，精准评估你的知识掌握度与认知负荷， 定位学习薄弱环节</p>
          <ul class="feature-card-points">
            <li><CheckCircleOutlined /> 知识点掌握度雷达图</li>
            <li><CheckCircleOutlined /> 认知负荷多维分析</li>
            <li><CheckCircleOutlined /> 智能薄弱点定位</li>
          </ul>
          <a-button type="link" class="feature-card-link" @click="goTo('/diagnose')">
            立即诊断 <ArrowRightOutlined />
          </a-button>
        </div>

        <!-- 路径规划 -->
        <div class="feature-card feature-card--featured">
          <div class="feature-badge">核心</div>
          <div
            class="feature-card-icon"
            style="
              background: linear-gradient(
                135deg,
                rgba(212, 163, 115, 0.25),
                rgba(212, 163, 115, 0.08)
              );
              color: #d4a373;
            "
          >
            <NodeIndexOutlined />
          </div>
          <h3>路径规划</h3>
          <p>采用 AOO 野燕麦优化算法，结合诊断结果自动生成专属学习路径， 甘特图直观管理学习计划</p>
          <ul class="feature-card-points">
            <li><CheckCircleOutlined /> AOO 智能优化调度</li>
            <li><CheckCircleOutlined /> 多方案对比择优</li>
            <li><CheckCircleOutlined /> 甘特图可视化进度</li>
          </ul>
          <a-button type="link" class="feature-card-link" @click="goTo('/path')">
            查看路径 <ArrowRightOutlined />
          </a-button>
        </div>

        <!-- 智能问答 -->
        <div class="feature-card">
          <div
            class="feature-card-icon"
            style="
              background: linear-gradient(135deg, rgba(0, 212, 255, 0.2), rgba(0, 212, 255, 0.08));
              color: #00d4ff;
            "
          >
            <RobotOutlined />
          </div>
          <h3>智能问答</h3>
          <p>基于 RAG 检索增强生成技术，结合星火大模型提供学科知识问答， 回答附带引用来源</p>
          <ul class="feature-card-points">
            <li><CheckCircleOutlined /> RAG 增强检索</li>
            <li><CheckCircleOutlined /> 引用来源可追溯</li>
            <li><CheckCircleOutlined /> 多学科知识库</li>
          </ul>
          <a-button type="link" class="feature-card-link" @click="goTo('/chat')">
            立即提问 <ArrowRightOutlined />
          </a-button>
        </div>
      </div>
    </section>

    <!-- =========================================================
         3. AOO 算法原理
         ========================================================= -->
    <section
      class="section algorithm-section"
      data-reveal-key="algorithm"
      :class="{ 'is-revealed': revealed['algorithm'] }"
    >
      <div class="section-header">
        <h2 class="section-title">AOO 算法原理</h2>
        <p class="section-desc">灵感源自野燕麦种子的传播与萌发过程，模拟自然界最优生存策略</p>
      </div>

      <div class="algorithm-flow">
        <!-- 流程 SVG 示意图 -->
        <div class="flow-diagram">
          <svg
            viewBox="0 0 960 200"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            class="flow-svg"
          >
            <!-- 连接线 -->
            <defs>
              <linearGradient id="lineGrad1" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stop-color="#4F7CFF" />
                <stop offset="100%" stop-color="#1677FF" />
              </linearGradient>
            </defs>

            <!-- 阶段连线 -->
            <path
              d="M138 55 Q210 55 270 55"
              stroke="rgba(148, 163, 184, 0.3)"
              stroke-width="2"
              stroke-dasharray="6 4"
            />
            <path
              d="M408 55 Q480 55 540 55"
              stroke="rgba(148, 163, 184, 0.3)"
              stroke-width="2"
              stroke-dasharray="6 4"
            />
            <path
              d="M678 55 Q750 55 810 55"
              stroke="rgba(148, 163, 184, 0.3)"
              stroke-width="2"
              stroke-dasharray="6 4"
            />

            <!-- 收敛箭头 -->
            <path
              d="M855 55 L880 55 L872 48 M880 55 L872 62"
              stroke="#D4A373"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />

            <!-- 阶段 1: 种子 -->
            <circle cx="90" cy="55" r="36" fill="url(#stage1Grad)" opacity="0.15" />
            <circle cx="90" cy="55" r="28" fill="url(#stage1Grad)" opacity="0.25" />
            <ellipse cx="90" cy="55" rx="14" ry="20" fill="url(#stage1Grad)" />
            <text
              x="90"
              y="118"
              text-anchor="middle"
              fill="#F8FAFC"
              font-size="14"
              font-weight="600"
            >
              种子初始化
            </text>
            <text x="90" y="138" text-anchor="middle" fill="#94A3B8" font-size="11">
              随机生成个体
            </text>

            <!-- 阶段 2: 扩散 -->
            <circle cx="345" cy="55" r="36" fill="url(#stage2Grad)" opacity="0.15" />
            <circle cx="345" cy="55" r="28" fill="url(#stage2Grad)" opacity="0.25" />
            <!-- 扩散箭头 -->
            <path
              d="M333 55 L320 42 M333 55 L320 68 M357 55 L370 42 M357 55 L370 68"
              stroke="url(#stage2Grad)"
              stroke-width="2"
              stroke-linecap="round"
            />
            <circle cx="345" cy="55" r="10" fill="url(#stage2Grad)" />
            <text
              x="345"
              y="118"
              text-anchor="middle"
              fill="#F8FAFC"
              font-size="14"
              font-weight="600"
            >
              扩散探索
            </text>
            <text x="345" y="138" text-anchor="middle" fill="#94A3B8" font-size="11">
              Levy 飞行搜索
            </text>

            <!-- 阶段 3: 滚动 -->
            <circle cx="615" cy="55" r="36" fill="url(#stage3Grad)" opacity="0.15" />
            <circle cx="615" cy="55" r="28" fill="url(#stage3Grad)" opacity="0.25" />
            <!-- 滚动箭头弧线 -->
            <path
              d="M597 70 Q615 90 633 70"
              stroke="url(#stage3Grad)"
              stroke-width="2"
              fill="none"
              stroke-linecap="round"
            />
            <circle cx="615" cy="55" r="10" fill="url(#stage3Grad)" />
            <text
              x="615"
              y="118"
              text-anchor="middle"
              fill="#F8FAFC"
              font-size="14"
              font-weight="600"
            >
              滚动开发
            </text>
            <text x="615" y="138" text-anchor="middle" fill="#94A3B8" font-size="11">
              局部精细化搜索
            </text>

            <!-- 阶段 4: 弹射 -->
            <circle cx="855" cy="55" r="36" fill="url(#stage4Grad)" opacity="0.15" />
            <circle cx="855" cy="55" r="28" fill="url(#stage4Grad)" opacity="0.25" />
            <!-- 弹射抛物线 -->
            <path
              d="M840 40 Q855 18 870 40"
              stroke="url(#stage4Grad)"
              stroke-width="2"
              fill="none"
              stroke-linecap="round"
            />
            <circle cx="855" cy="55" r="10" fill="url(#stage4Grad)" />
            <text
              x="855"
              y="118"
              text-anchor="middle"
              fill="#F8FAFC"
              font-size="14"
              font-weight="600"
            >
              弹射收敛
            </text>
            <text x="855" y="138" text-anchor="middle" fill="#94A3B8" font-size="11">
              逃避局部最优
            </text>

            <defs>
              <linearGradient
                id="stage1Grad"
                x1="76"
                y1="35"
                x2="104"
                y2="75"
                gradientUnits="userSpaceOnUse"
              >
                <stop stop-color="#1677FF" />
                <stop offset="1" stop-color="#4096FF" />
              </linearGradient>
              <linearGradient
                id="stage2Grad"
                x1="331"
                y1="35"
                x2="359"
                y2="75"
                gradientUnits="userSpaceOnUse"
              >
                <stop stop-color="#52C41A" />
                <stop offset="1" stop-color="#73D13D" />
              </linearGradient>
              <linearGradient
                id="stage3Grad"
                x1="601"
                y1="35"
                x2="629"
                y2="75"
                gradientUnits="userSpaceOnUse"
              >
                <stop stop-color="#FA8C16" />
                <stop offset="1" stop-color="#FFA940" />
              </linearGradient>
              <linearGradient
                id="stage4Grad"
                x1="841"
                y1="35"
                x2="869"
                y2="75"
                gradientUnits="userSpaceOnUse"
              >
                <stop stop-color="#722ED1" />
                <stop offset="1" stop-color="#9254DE" />
              </linearGradient>
            </defs>
          </svg>
        </div>

        <!-- 算法特性说明 -->
        <div class="flow-description">
          <div class="flow-desc-item">
            <div class="flow-desc-dot" style="background: #4a6cf7" />
            <div>
              <strong>启发式搜索</strong>
              <span>模拟野燕麦种子通过风、水、动物三种传播方式的探索策略</span>
            </div>
          </div>
          <div class="flow-desc-item">
            <div class="flow-desc-dot" style="background: #34d399" />
            <div>
              <strong>Lévy 飞行</strong>
              <span>兼顾大范围探索与局部精细化搜索，避免陷入局部最优</span>
            </div>
          </div>
          <div class="flow-desc-item">
            <div class="flow-desc-dot" style="background: #fbbf24" />
            <div>
              <strong>动态参数</strong>
              <span>c = 1-(t/T)³ 立方衰减策略，平滑过渡探索与开发阶段</span>
            </div>
          </div>
          <div class="flow-desc-item">
            <div class="flow-desc-dot" style="background: #a78bfa" />
            <div>
              <strong>弹射逃逸</strong>
              <span>模拟燕麦种子弹射传播，帮助种群跳出局部最优陷阱</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- =========================================================
         4. 核心优势
         ========================================================= -->
    <section
      class="section advantages-section"
      data-reveal-key="advantages"
      :class="{ 'is-revealed': revealed['advantages'] }"
    >
      <div class="section-header">
        <h2 class="section-title">为什么选择燕麦智导</h2>
        <p class="section-desc">三大核心优势，定义智慧学习新范式</p>
      </div>

      <div class="advantages-grid">
        <!-- 个性化 -->
        <div class="advantage-card">
          <div class="advantage-icon-wrap">
            <svg viewBox="0 0 64 64" fill="none" class="advantage-icon-svg">
              <circle cx="32" cy="32" r="28" fill="url(#adv1Bg)" />
              <path
                d="M32 16 C24 16 20 22 20 28 C20 38 32 48 32 48 C32 48 44 38 44 28 C44 22 40 16 32 16Z"
                fill="url(#adv1Fg)"
              />
              <circle cx="32" cy="28" r="5" fill="white" opacity="0.6" />
              <defs>
                <linearGradient
                  id="adv1Bg"
                  x1="4"
                  y1="4"
                  x2="60"
                  y2="60"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#E6F4FF" />
                  <stop offset="1" stop-color="#BAE0FF" />
                </linearGradient>
                <linearGradient
                  id="adv1Fg"
                  x1="20"
                  y1="16"
                  x2="44"
                  y2="48"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#1677FF" />
                  <stop offset="1" stop-color="#4096FF" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h3>个性化</h3>
          <p>
            每个人的认知地图独一无二。我们通过诊断分析精准建模，为每位学习者定制专属学习路径，
            真正做到因材施教
          </p>
          <ul class="advantage-tags">
            <li>认知建模</li>
            <li>自适应诊断</li>
            <li>专属路径</li>
          </ul>
        </div>

        <!-- 智能化 -->
        <div class="advantage-card">
          <div class="advantage-icon-wrap">
            <svg viewBox="0 0 64 64" fill="none" class="advantage-icon-svg">
              <circle cx="32" cy="32" r="28" fill="url(#adv2Bg)" />
              <circle cx="32" cy="32" r="14" fill="url(#adv2Fg)" opacity="0.3" />
              <circle cx="32" cy="32" r="6" fill="url(#adv2Fg)" />
              <line
                x1="32"
                y1="14"
                x2="32"
                y2="26"
                stroke="url(#adv2Fg)"
                stroke-width="2.5"
                stroke-linecap="round"
              />
              <line
                x1="32"
                y1="38"
                x2="32"
                y2="50"
                stroke="url(#adv2Fg)"
                stroke-width="2.5"
                stroke-linecap="round"
              />
              <line
                x1="14"
                y1="32"
                x2="26"
                y2="32"
                stroke="url(#adv2Fg)"
                stroke-width="2.5"
                stroke-linecap="round"
              />
              <line
                x1="38"
                y1="32"
                x2="50"
                y2="32"
                stroke="url(#adv2Fg)"
                stroke-width="2.5"
                stroke-linecap="round"
              />
              <defs>
                <linearGradient
                  id="adv2Bg"
                  x1="4"
                  y1="4"
                  x2="60"
                  y2="60"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#F6FFED" />
                  <stop offset="1" stop-color="#D9F7BE" />
                </linearGradient>
                <linearGradient
                  id="adv2Fg"
                  x1="14"
                  y1="14"
                  x2="50"
                  y2="50"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#52C41A" />
                  <stop offset="1" stop-color="#73D13D" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h3>智能化</h3>
          <p>
            融合 AOO 群体智能优化算法与 RAG 大语言模型， 从路径规划到知识问答，AI 全链路赋能学习过程
          </p>
          <ul class="advantage-tags">
            <li>AOO 算法</li>
            <li>RAG 问答</li>
            <li>大模型驱动</li>
          </ul>
        </div>

        <!-- 可解释 -->
        <div class="advantage-card">
          <div class="advantage-icon-wrap">
            <svg viewBox="0 0 64 64" fill="none" class="advantage-icon-svg">
              <circle cx="32" cy="32" r="28" fill="url(#adv3Bg)" />
              <rect x="16" y="22" width="32" height="26" rx="3" fill="url(#adv3Fg)" />
              <line
                x1="24"
                y1="30"
                x2="40"
                y2="30"
                stroke="white"
                stroke-width="2"
                stroke-linecap="round"
                opacity="0.8"
              />
              <line
                x1="24"
                y1="36"
                x2="36"
                y2="36"
                stroke="white"
                stroke-width="2"
                stroke-linecap="round"
                opacity="0.8"
              />
              <line
                x1="24"
                y1="42"
                x2="38"
                y2="42"
                stroke="white"
                stroke-width="2"
                stroke-linecap="round"
                opacity="0.8"
              />
              <defs>
                <linearGradient
                  id="adv3Bg"
                  x1="4"
                  y1="4"
                  x2="60"
                  y2="60"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#F9F0FF" />
                  <stop offset="1" stop-color="#EFDBFF" />
                </linearGradient>
                <linearGradient
                  id="adv3Fg"
                  x1="16"
                  y1="22"
                  x2="48"
                  y2="48"
                  gradientUnits="userSpaceOnUse"
                >
                  <stop stop-color="#722ED1" />
                  <stop offset="1" stop-color="#9254DE" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h3>可解释</h3>
          <p>
            诊断报告附带详细分析说明，路径推荐展示优化得分与收敛曲线，
            智能问答标注引用来源，每一步都有据可依
          </p>
          <ul class="advantage-tags">
            <li>诊断报告</li>
            <li>收敛可视化</li>
            <li>来源追溯</li>
          </ul>
        </div>
      </div>
    </section>

    <!-- =========================================================
         5. 数据统计
         ========================================================= -->
    <section
      v-if="statsLoaded"
      class="section stats-section"
      data-reveal-key="stats"
      :class="{ 'is-revealed': revealed['stats'] }"
    >
      <div class="stats-inner">
        <div class="stat-item">
          <div class="stat-value">
            <span class="stat-number">{{ displayCounts.paths.toLocaleString() }}</span>
          </div>
          <div class="stat-label">已生成学习路径</div>
          <div class="stat-icon-bg">
            <NodeIndexOutlined />
          </div>
        </div>
        <div class="stat-divider" />
        <div class="stat-item">
          <div class="stat-value">
            <span class="stat-number">{{ displayCounts.knowledgePoints.toLocaleString() }}</span>
          </div>
          <div class="stat-label">覆盖知识点</div>
          <div class="stat-icon-bg">
            <BulbOutlined />
          </div>
        </div>
        <div class="stat-divider" />
        <div class="stat-item">
          <div class="stat-value">
            <span class="stat-number">{{ displayCounts.users.toLocaleString() }}</span>
          </div>
          <div class="stat-label">平台用户</div>
          <div class="stat-icon-bg">
            <TeamOutlined />
          </div>
        </div>
      </div>
    </section>

    <!-- =========================================================
         6. 页脚
         ========================================================= -->
    <footer class="footer">
      <div class="footer-inner">
        <!-- 左侧：品牌 + 简介 -->
        <div class="footer-brand">
          <div class="footer-logo">
            <svg viewBox="0 0 40 40" fill="none" class="footer-logo-svg">
              <ellipse cx="20" cy="26" rx="7" ry="10" fill="#D4C08C" />
              <path d="M20 18 L17 6" stroke="#C4A862" stroke-width="1.5" stroke-linecap="round" />
              <path d="M20 18 L23 5" stroke="#C4A862" stroke-width="1.5" stroke-linecap="round" />
              <path d="M20 18 L20 4" stroke="#C4A862" stroke-width="1.5" stroke-linecap="round" />
              <circle
                cx="20"
                cy="20"
                r="18"
                stroke="#4F7CFF"
                stroke-width="1"
                fill="none"
                opacity="0.4"
              />
            </svg>
            <span class="footer-brand-name">燕麦智导</span>
          </div>
          <p class="footer-desc">
            针对应用型高校人工智能通识课"统一教学"与"个体差异"的矛盾，本课题依托认知负荷理论，以团队前期ESI高被引的AOO算法为工具，构建多目标学习路径推荐模型。通过认知诊断识别学生认知负荷与知识掌握水平，以学习效果最大化和认知负荷最小化为目标，通过AOO算法求解最优学习路径。准实验验证该路径对学习效果的提升及负荷的降低效果，为人工智能通识课从经验驱动向算法驱动的精准教学转型提供依据。
          </p>
        </div>

        <!-- 中间：快捷导航 -->
        <div class="footer-nav">
          <h4>快捷入口</h4>
          <template v-if="userStore.isTeacher">
            <a @click="goTo('/teacher')">教师仪表盘</a>
            <a @click="goTo('/teacher/knowledge')">知识点管理</a>
            <a @click="goTo('/teacher/questions')">题库管理</a>
          </template>
          <template v-else>
            <a @click="goTo('/diagnose')">认知诊断</a>
            <a @click="goTo('/path')">我的路径</a>
            <a @click="goTo('/chat')">智能问答</a>
            <a @click="goTo('/dashboard')">学情看板</a>
          </template>
        </div>

        <!-- 右侧：赛事 & 团队 -->
        <div class="footer-info">
          <h4>赛事信息</h4>
          <div class="footer-info-item">
            <TrophyOutlined />
            <span>挑战杯 · 全国大学生课外学术科技作品竞赛</span>
          </div>
          <div class="footer-info-item">
            <TeamOutlined />
            <span>燕麦智导项目团队</span>
          </div>
          <div class="footer-info-item">
            <EnvironmentOutlined />
            <span>北方工业大学人工智能与计算机学院</span>
          </div>
          <div class="footer-info-item">
            <EnvironmentOutlined />
            <span>北方工业大学伦敦布鲁内尔学院</span>
          </div>
        </div>
      </div>

      <!-- 版权栏 -->
      <div class="footer-bottom">
        <div class="footer-bottom-left">
          <span
            >&copy; {{ new Date().getFullYear() }} 燕麦智导 · OatGuide. All rights reserved.</span
          >
        </div>
        <div class="footer-bottom-right">
          <a href="https://github.com/Joyce-SUN-41/AOOGuidePathPlanning" target="_blank" rel="noopener" class="footer-social-link">
            <GithubOutlined class="footer-social-icon" />
          </a>
          <a href="https://ai.fifedu.com/agent/landings/HomeCompetition" target="_blank" rel="noopener" class="footer-social-link">
            <GlobalOutlined class="footer-social-icon" />
          </a>
          <a href="mailto:sunhaoran0401@126.com" class="footer-social-link">
            <MailOutlined class="footer-social-icon" />
          </a>
        </div>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* ============================================================
   变量 — 深色科技风
   ============================================================ */
.home-page {
  --color-primary: #4a6cf7;
  --color-primary-dark: #3b54d4;
  --color-accent: #00d4ff;
  --color-oat: #d4a373;
  --color-oat-light: #faedcd;
  --radius-card: 20px;
  --radius-btn: 12px;
  --transition-card: 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

/* ============================================================
   通用 Section
   ============================================================ */
.section {
  margin-bottom: 80px;
  opacity: 0;
  transform: translateY(40px);
  transition:
    opacity 0.7s ease,
    transform 0.7s ease;
}

.section.is-revealed {
  opacity: 1;
  transform: translateY(0);
}

.section-header {
  text-align: center;
  margin-bottom: 48px;
}

.section-title {
  font-size: 32px;
  font-weight: 700;
  color: #f8fafc;
  margin: 0 0 12px 0;
  letter-spacing: -0.5px;
}

.section-desc {
  font-size: 16px;
  color: #94a3b8;
  margin: 0;
  line-height: 1.6;
}

/* ============================================================
   1. Hero 区域 — 深空 + 燕麦金径向光晕
   ============================================================ */
.hero {
  position: relative;
  min-height: 520px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 80px 40px 60px;
  overflow: hidden;
  border-radius: 24px;
  margin-bottom: 24px;
  background: linear-gradient(160deg, #141b2b 0%, #101726 30%, #0f1623 60%, #0a0d14 100%);
}

/* Hero 燕麦金光晕 */
.hero::before {
  content: '';
  position: absolute;
  top: -20%;
  left: 50%;
  transform: translateX(-50%);
  width: 600px;
  height: 400px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(212, 163, 115, 0.15) 0%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}

/* 背景光斑 + 流沙层 */
.hero-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  border-radius: inherit;
  overflow: hidden;
}

.hero-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.35;
}

.hero-orb--1 {
  width: 320px;
  height: 320px;
  top: -80px;
  left: -60px;
  background: rgba(74, 108, 247, 0.18);
  animation: orb-float-1 12s ease-in-out infinite;
}

.hero-orb--2 {
  width: 260px;
  height: 260px;
  top: 50%;
  right: -80px;
  background: rgba(0, 212, 255, 0.12);
  transform: translateY(-50%);
  animation: orb-float-2 14s ease-in-out infinite;
}

.hero-orb--3 {
  width: 200px;
  height: 200px;
  bottom: -40px;
  left: 30%;
  background: rgba(212, 163, 115, 0.18);
  animation: orb-float-3 16s ease-in-out infinite;
}

@keyframes orb-float-1 {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }
  25% {
    transform: translate(20px, -15px) scale(1.05);
  }
  50% {
    transform: translate(-10px, -25px) scale(0.95);
  }
  75% {
    transform: translate(-20px, -5px) scale(1.02);
  }
}

@keyframes orb-float-2 {
  0%,
  100% {
    transform: translateY(-50%) translate(0, 0) scale(1);
  }
  25% {
    transform: translateY(-50%) translate(-25px, 10px) scale(1.08);
  }
  50% {
    transform: translateY(-50%) translate(10px, -15px) scale(0.93);
  }
  75% {
    transform: translateY(-50%) translate(25px, 5px) scale(1.04);
  }
}

@keyframes orb-float-3 {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }
  33% {
    transform: translate(-15px, -10px) scale(1.06);
  }
  66% {
    transform: translate(15px, 10px) scale(0.94);
  }
}

.hero-inner {
  position: relative;
  z-index: 1;
  max-width: 720px;
}

/* 品牌区域 */
.hero-brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-bottom: 24px;
}

.hero-logo {
  width: 72px;
  height: 72px;
  flex-shrink: 0;
}

.hero-logo svg {
  width: 100%;
  height: 100%;
}

.hero-name {
  font-size: 44px;
  font-weight: 800;
  margin: 0;
  background: linear-gradient(135deg, #f8fafc 0%, #d4a373 50%, #faedcd 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -1px;
}

/* 标语 */
.hero-tagline {
  font-size: 20px;
  font-weight: 500;
  color: #e2e8f0;
  line-height: 1.6;
  margin: 0 0 12px 0;
}

/* 副标题 — 带燕麦金渐变下划线，文字投影增强可读性 */
.hero-subtitle {
  font-size: 15px;
  color: #cbd5e1;
  line-height: 1.8;
  margin: 0 0 32px 0;
  max-width: 600px;
  margin-left: auto;
  margin-right: auto;
  padding-bottom: 8px;
  border-bottom: 2px solid;
  border-image: linear-gradient(90deg, transparent 10%, #d4a373 50%, transparent 90%) 1;
  text-shadow: 0 1px 8px rgba(10, 13, 20, 0.8), 0 0 2px rgba(10, 13, 20, 0.6);
}

.text-accent {
  color: #d4a373;
  font-weight: 600;
}

/* CTA 按钮 */
.hero-actions {
  display: flex;
  gap: 16px;
  justify-content: center;
  flex-wrap: wrap;
}

.hero-btn {
  height: 48px;
  font-weight: 600;
  font-size: 15px;
  border-radius: var(--radius-btn);
  padding: 0 28px;
  transition: all var(--transition-card);
}

.hero-btn--primary {
  background: linear-gradient(135deg, #d4a373, #c08b5c);
  border: none;
  color: #0a0d14;
  box-shadow: 0 4px 16px rgba(212, 163, 115, 0.35);
}

.hero-btn--primary:hover {
  background: linear-gradient(135deg, #e8cb8f, #d4a373);
  box-shadow: 0 6px 24px rgba(212, 163, 115, 0.45);
  transform: translateY(-2px);
}

.hero-btn--ghost {
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(12px);
}

.hero-btn--ghost:hover {
  border-color: #d4a373;
  color: #d4a373;
  background: rgba(212, 163, 115, 0.08);
  transform: translateY(-2px);
}

/* 滚动提示 */
.hero-scroll-hint {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1;
}

.scroll-dot {
  display: block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #d4a373;
  animation: scrollPulse 2s ease-in-out infinite;
}

@keyframes scrollPulse {
  0%,
  100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  50% {
    opacity: 1;
    transform: translateY(6px);
  }
}

/* ============================================================
   2. 核心功能卡片
   ============================================================ */
.features-section {
  padding-top: 32px;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}

/* 交错淡入 */
.features-section.is-revealed .feature-card:nth-child(1) {
  transition-delay: 0.1s;
}
.features-section.is-revealed .feature-card:nth-child(2) {
  transition-delay: 0.2s;
}
.features-section.is-revealed .feature-card:nth-child(3) {
  transition-delay: 0.3s;
}

.feature-card {
  position: relative;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px);
  border-radius: var(--radius-card);
  padding: 32px 28px 24px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: all var(--transition-card);
  display: flex;
  flex-direction: column;
  opacity: 0;
  transform: translateY(30px);
}

.features-section.is-revealed .feature-card {
  opacity: 1;
  transform: translateY(0);
}

.feature-card:hover {
  transform: translateY(-6px);
  box-shadow:
    0 16px 48px rgba(0, 0, 0, 0.35),
    0 0 0 1px rgba(212, 163, 115, 0.12);
  border-color: rgba(212, 163, 115, 0.2);
}

/* 核心卡片：微光边框效果 */
.feature-card--featured {
  border-color: rgba(212, 163, 115, 0.18);
  background: linear-gradient(180deg, rgba(212, 163, 115, 0.06) 0%, rgba(255, 255, 255, 0.04) 40%);
}

.feature-card--featured::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: inherit;
  padding: 1px;
  background: linear-gradient(
    135deg,
    rgba(212, 163, 115, 0.3),
    rgba(74, 108, 247, 0.15),
    rgba(212, 163, 115, 0.3)
  );
  -webkit-mask:
    linear-gradient(#fff 0 0) content-box,
    linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
  z-index: -1;
  animation: border-shift 4s ease-in-out infinite;
}

@keyframes border-shift {
  0%,
  100% {
    opacity: 0.6;
  }
  50% {
    opacity: 1;
  }
}

.feature-card--featured:hover {
  border-color: rgba(212, 163, 115, 0.3);
  transform: translateY(-6px);
  box-shadow:
    0 20px 52px rgba(0, 0, 0, 0.4),
    0 0 40px rgba(212, 163, 115, 0.08);
}

.feature-badge {
  position: absolute;
  top: -12px;
  right: 24px;
  background: linear-gradient(135deg, #d4a373, #c08b5c);
  color: #0a0d14;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 12px;
  border-radius: 20px;
  box-shadow: 0 2px 8px rgba(212, 163, 115, 0.35);
}

.feature-card-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  margin-bottom: 20px;
  backdrop-filter: blur(8px);
  transition:
    transform 0.3s ease,
    box-shadow 0.3s ease;
}

.feature-card:hover .feature-card-icon {
  transform: scale(1.08);
}

.feature-card h3 {
  font-size: 20px;
  font-weight: 700;
  color: #f8fafc;
  margin: 0 0 8px 0;
}

.feature-card > p {
  font-size: 14px;
  color: #94a3b8;
  line-height: 1.7;
  margin: 0 0 16px 0;
}

.feature-card-points {
  list-style: none;
  padding: 0;
  margin: 0 0 16px 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.feature-card-points li {
  font-size: 13px;
  color: #94a3b8;
  display: flex;
  align-items: center;
  gap: 6px;
}

.feature-card-points li :deep(.anticon) {
  color: #34d399;
  font-size: 14px;
}

.feature-card-link {
  margin-top: auto;
  padding: 6px 0 !important;
  font-weight: 600;
  font-size: 14px;
  color: #d4a373;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: gap 0.2s;
  width: fit-content;
}

.feature-card:hover .feature-card-link {
  gap: 8px;
  color: #faedcd;
}

/* ============================================================
   3. AOO 算法原理
   ============================================================ */
.algorithm-section {
  /* extra padding for visibility */
}

.algorithm-flow {
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px);
  border-radius: var(--radius-card);
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 40px 36px;
  overflow: hidden;
}

.flow-diagram {
  margin-bottom: 32px;
}

.flow-svg {
  width: 100%;
  height: auto;
  max-height: 200px;
}

.flow-description {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.flow-desc-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.flow-desc-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 4px;
}

.flow-desc-item div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.flow-desc-item strong {
  font-size: 14px;
  color: #f8fafc;
}

.flow-desc-item span {
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.6;
}

/* ============================================================
   4. 核心优势
   ============================================================ */
.advantages-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}

.advantage-card {
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px);
  border-radius: var(--radius-card);
  padding: 36px 28px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  text-align: center;
  transition: all var(--transition-card);
  display: flex;
  flex-direction: column;
  align-items: center;
}

.advantage-card:hover {
  transform: translateY(-4px);
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.35),
    0 0 0 1px rgba(212, 163, 115, 0.1);
  border-color: rgba(212, 163, 115, 0.18);
}

.advantage-icon-wrap {
  width: 72px;
  height: 72px;
  margin-bottom: 20px;
}

.advantage-icon-svg {
  width: 100%;
  height: 100%;
}

.advantage-card h3 {
  font-size: 20px;
  font-weight: 700;
  color: #f8fafc;
  margin: 0 0 10px 0;
}

.advantage-card > p {
  font-size: 14px;
  color: #94a3b8;
  line-height: 1.7;
  margin: 0 0 16px 0;
}

.advantage-tags {
  list-style: none;
  padding: 0;
  margin: auto 0 0 0;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.advantage-tags li {
  font-size: 12px;
  color: #d4a373;
  background: rgba(212, 163, 115, 0.1);
  border: 1px solid rgba(212, 163, 115, 0.15);
  padding: 3px 10px;
  border-radius: 6px;
  font-weight: 500;
}

/* ============================================================
   5. 数据统计
   ============================================================ */
.stats-section {
  background: linear-gradient(135deg, rgba(212, 163, 115, 0.08), rgba(20, 27, 43, 0.95));
  border: 1px solid rgba(212, 163, 115, 0.1);
  border-radius: var(--radius-card);
  padding: 0;
  overflow: hidden;
}

.stats-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 56px 48px;
}

.stat-item {
  flex: 1;
  text-align: center;
  position: relative;
}

.stat-value {
  display: flex;
  align-items: baseline;
  justify-content: center;
  margin-bottom: 8px;
}

.stat-number {
  font-size: 48px;
  font-weight: 800;
  color: #d4a373;
  line-height: 1;
  letter-spacing: -1px;
  font-family: 'JetBrains Mono', monospace;
}

.stat-plus,
.stat-unit {
  font-size: 24px;
  font-weight: 700;
  color: rgba(212, 163, 115, 0.6);
  margin-left: 2px;
}

.stat-label {
  font-size: 15px;
  color: #94a3b8;
  font-weight: 500;
  position: relative;
  z-index: 1;
}

.stat-icon-bg {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 80px;
  color: rgba(212, 163, 115, 0.04);
  pointer-events: none;
  z-index: 0;
}

.stat-divider {
  width: 1px;
  height: 60px;
  background: rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

/* ============================================================
   6. 页脚
   ============================================================ */
.footer {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding-top: 56px;
  margin-top: 40px;
}

.footer-inner {
  display: grid;
  grid-template-columns: 1.5fr 1fr 1.2fr;
  gap: 48px;
  padding-bottom: 48px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.footer-brand {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.footer-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.footer-logo-svg {
  width: 36px;
  height: 36px;
}

.footer-brand-name {
  font-size: 20px;
  font-weight: 700;
  color: #f8fafc;
}

.footer-desc {
  font-size: 13px;
  color: #94a3b8;
  line-height: 1.7;
  margin: 0;
  max-width: 570px;
  padding-left: 46px;
}

.footer-nav h4,
.footer-info h4 {
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
  margin: 0 0 16px 0;
}

.footer-nav {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.footer-nav a {
  font-size: 13px;
  color: #94a3b8;
  cursor: pointer;
  transition: color 0.2s;
  user-select: none;
}

.footer-nav a:hover {
  color: #d4a373;
}

.footer-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.footer-info-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #94a3b8;
}

.footer-info-item :deep(.anticon) {
  color: #64748b;
  font-size: 15px;
}

.footer-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 0 24px;
}

.footer-bottom-left {
  font-size: 12px;
  color: #64748b;
}

.footer-bottom-right {
  display: flex;
  gap: 16px;
}

.footer-social-link {
  display: flex;
  align-items: center;
  color: inherit;
  text-decoration: none;
}

.footer-social-icon {
  font-size: 18px;
  color: #64748b;
  cursor: pointer;
  transition: color 0.2s;
}

.footer-social-link:hover .footer-social-icon {
  color: #d4a373;
}

/* ============================================================
   响应式设计
   ============================================================ */

/* 平板 */
@media (max-width: 1024px) {
  .features-grid,
  .advantages-grid {
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  }

  .flow-description {
    grid-template-columns: repeat(2, 1fr);
  }

  .flow-svg {
    max-height: 160px;
  }

  .footer-inner {
    grid-template-columns: 1fr 1fr;
    gap: 36px;
  }

  .footer-brand {
    grid-column: 1 / -1;
  }
}

/* 手机 */
@media (max-width: 768px) {
  .hero {
    padding: 56px 20px 48px;
    min-height: auto;
    border-radius: 16px;
  }

  .hero-logo {
    width: 56px;
    height: 56px;
  }

  .hero-name {
    font-size: 32px;
  }

  .hero-tagline {
    font-size: 17px;
  }

  .hero-subtitle {
    font-size: 14px;
  }

  .hero-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-btn {
    width: 100%;
    justify-content: center;
  }

  .section {
    margin-bottom: 56px;
  }

  .section-title {
    font-size: 26px;
  }

  .section-header {
    margin-bottom: 32px;
  }

  .features-grid {
    grid-template-columns: 1fr;
  }

  .algorithm-flow {
    padding: 24px 16px;
  }

  .flow-diagram {
    display: none; /* 小屏幕隐藏 SVG，保留文字说明 */
  }

  .flow-description {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .advantages-grid {
    grid-template-columns: 1fr;
  }

  .stats-inner {
    flex-direction: column;
    gap: 32px;
    padding: 40px 24px;
  }

  .stat-divider {
    width: 80px;
    height: 1px;
  }

  .stat-number {
    font-size: 36px;
  }

  .footer-inner {
    grid-template-columns: 1fr;
    gap: 32px;
  }

  .footer-bottom {
    flex-direction: column;
    gap: 12px;
    text-align: center;
  }

  .hero-scroll-hint {
    display: none;
  }
}
</style>
