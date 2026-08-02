<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import type { LoginParams } from '@/types'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import {
  UserOutlined,
  LockOutlined,
  TeamOutlined,
  ArrowRightOutlined
} from '@ant-design/icons-vue'
import OatDispersalBackground from '@/components/OatDispersalBackground.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formRef = ref<FormInstance>()
const loading = ref(false)

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

async function handleLogin() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  loading.value = true
  try {
    const success = await userStore.login(formState)
    if (success) {
      const redirect = (route.query['redirect'] as string) || '/home'
      router.push(redirect)
    }
  } finally {
    loading.value = false
  }
}

function demoLogin(role: 'student' | 'teacher') {
  formState.username = role === 'student' ? 'student_demo' : 'teacher_demo'
  formState.password = '123456'
  handleLogin()
}
</script>

<template>
  <div class="login-page">
    <OatDispersalBackground :density="42" :opacity="0.5" />

    <!-- 环境光斑 -->
    <div class="login-ambient" aria-hidden="true">
      <span class="orb orb--1" />
      <span class="orb orb--2" />
      <span class="orb orb--3" />
      <div class="grid-fade" />
    </div>

    <div class="login-shell">
      <!-- 品牌叙事区 -->
      <section class="brand-panel">
        <div class="brand-panel__glow" aria-hidden="true" />

        <div class="brand-content">
          <div class="brand-mark">
            <div class="brand-logo">
              <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <ellipse cx="40" cy="52" rx="12" ry="18" fill="url(#loginOatGrad)" opacity="0.95" />
                <ellipse cx="37" cy="47" rx="5" ry="8" fill="white" opacity="0.2" />
                <path d="M40 34 L34 12" stroke="url(#loginAwnGrad)" stroke-width="2" stroke-linecap="round" />
                <path d="M40 34 L46 10" stroke="url(#loginAwnGrad)" stroke-width="2" stroke-linecap="round" />
                <path d="M40 34 L40 8" stroke="url(#loginAwnGrad)" stroke-width="2" stroke-linecap="round" />
                <path
                  d="M32 55 Q18 48 10 56"
                  stroke="url(#loginLeafGrad)"
                  stroke-width="2.5"
                  fill="none"
                  stroke-linecap="round"
                />
                <path
                  d="M48 55 Q62 48 70 56"
                  stroke="url(#loginLeafGrad)"
                  stroke-width="2.5"
                  fill="none"
                  stroke-linecap="round"
                />
                <circle
                  cx="40"
                  cy="40"
                  r="36"
                  stroke="url(#loginRingGrad)"
                  stroke-width="1.5"
                  fill="none"
                  opacity="0.55"
                  class="logo-ring"
                />
                <defs>
                  <linearGradient id="loginOatGrad" x1="28" y1="34" x2="52" y2="70" gradientUnits="userSpaceOnUse">
                    <stop stop-color="#D4C08C" />
                    <stop offset="0.5" stop-color="#C4A862" />
                    <stop offset="1" stop-color="#A88B3E" />
                  </linearGradient>
                  <linearGradient id="loginAwnGrad" x1="40" y1="34" x2="40" y2="8" gradientUnits="userSpaceOnUse">
                    <stop stop-color="#C4A862" />
                    <stop offset="1" stop-color="#8B6914" />
                  </linearGradient>
                  <linearGradient id="loginLeafGrad" x1="10" y1="56" x2="70" y2="56" gradientUnits="userSpaceOnUse">
                    <stop stop-color="#7BA05B" />
                    <stop offset="1" stop-color="#5D8A3C" />
                  </linearGradient>
                  <linearGradient id="loginRingGrad" x1="4" y1="4" x2="76" y2="76" gradientUnits="userSpaceOnUse">
                    <stop stop-color="#D4A373" />
                    <stop offset="1" stop-color="#4A6CF7" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <h1 class="brand-name">燕麦智导</h1>
          </div>

          <p class="brand-tagline">让野燕麦的生存智慧，重塑每一个学习者的认知地图</p>
          <p class="brand-support">
            AOO 优化算法驱动认知诊断、个性化路径与智能问答——登录后，你的学习轨迹开始收敛。
          </p>

          <!-- 路径隐喻：种子收敛轨迹 -->
          <div class="path-visual" aria-hidden="true">
            <svg class="path-svg" viewBox="0 0 360 120" fill="none">
              <path
                class="path-line path-line--a"
                d="M20 90 C80 90, 100 30, 160 40 S240 100, 340 28"
                stroke="url(#loginPathGrad)"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <path
                class="path-line path-line--b"
                d="M20 70 C90 70, 120 100, 180 60 S260 20, 340 50"
                stroke="rgba(0,212,255,0.35)"
                stroke-width="1"
                stroke-linecap="round"
              />
              <circle class="path-node path-node--1" cx="20" cy="90" r="3.5" fill="#D4A373" />
              <circle class="path-node path-node--2" cx="160" cy="40" r="3" fill="#4A6CF7" />
              <circle class="path-node path-node--3" cx="340" cy="28" r="4.5" fill="#00D4FF" />
              <defs>
                <linearGradient id="loginPathGrad" x1="20" y1="90" x2="340" y2="28">
                  <stop stop-color="#D4A373" stop-opacity="0.2" />
                  <stop offset="0.5" stop-color="#D4A373" stop-opacity="0.85" />
                  <stop offset="1" stop-color="#00D4FF" stop-opacity="0.9" />
                </linearGradient>
              </defs>
            </svg>
            <div class="path-labels">
              <span>探索</span>
              <span>收敛</span>
              <span>最优路径</span>
            </div>
          </div>

          <ul class="brand-pillars">
            <li style="--i: 0"><span class="pillar-dot" />AI 认知诊断</li>
            <li style="--i: 1"><span class="pillar-dot" />AOO 路径规划</li>
            <li style="--i: 2"><span class="pillar-dot" />RAG 智能问答</li>
          </ul>
        </div>
      </section>

      <!-- 登录交互区 -->
      <section class="form-panel">
        <div class="form-card">
          <header class="form-header">
            <p class="form-eyebrow">Welcome back</p>
            <h2 class="form-title">进入认知地图</h2>
            <p class="form-subtitle">登录账号，继续你的个性化学习旅程</p>
          </header>

          <a-form
            ref="formRef"
            :model="formState"
            :rules="rules"
            layout="vertical"
            size="large"
            class="login-form"
            @finish="handleLogin"
          >
            <a-form-item name="username">
              <a-input
                v-model:value="formState.username"
                placeholder="请输入用户名"
                autocomplete="username"
                class="login-input"
              >
                <template #prefix>
                  <UserOutlined class="input-icon" />
                </template>
              </a-input>
            </a-form-item>

            <a-form-item name="password">
              <a-input-password
                v-model:value="formState.password"
                placeholder="请输入密码"
                autocomplete="current-password"
                class="login-input"
              >
                <template #prefix>
                  <LockOutlined class="input-icon" />
                </template>
              </a-input-password>
            </a-form-item>

            <div class="form-extra">
              <a-checkbox v-model:checked="formState.remember">记住登录状态</a-checkbox>
            </div>

            <a-form-item class="submit-item">
              <button type="submit" class="login-btn" :disabled="loading" :class="{ 'is-loading': loading }">
                <span class="login-btn__label">{{ loading ? '正在进入…' : '登 录' }}</span>
                <ArrowRightOutlined v-if="!loading" class="login-btn__arrow" />
                <span v-else class="login-btn__spinner" />
              </button>
            </a-form-item>
          </a-form>

          <div class="demo-section">
            <div class="demo-divider"><span>快速体验</span></div>
            <div class="demo-buttons">
              <button type="button" class="demo-btn demo-btn--student" @click="demoLogin('student')">
                <UserOutlined />
                学生 Demo
              </button>
              <button type="button" class="demo-btn demo-btn--teacher" @click="demoLogin('teacher')">
                <TeamOutlined />
                教师 Demo
              </button>
            </div>
          </div>

          <footer class="form-footer">
            <span>还没有账号？</span>
            <button type="button" class="link-btn" @click="router.push('/register')">立即注册</button>
          </footer>
        </div>

        <p class="form-credit">燕麦智导 · OatGuide</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* ============================================================
   登录页 — 深空构图 + 燕麦种子传播动效
   ============================================================ */
.login-page {
  --oat: #d4a373;
  --oat-soft: #faedcd;
  --aurora: #4a6cf7;
  --cyan: #00d4ff;
  --ink: #0a0d14;
  --panel: #141b2b;
  --text: #f8fafc;
  --muted: #94a3b8;
  --dim: #64748b;

  position: relative;
  min-height: 100vh;
  overflow: hidden;
  background: linear-gradient(155deg, #141b2b 0%, #101726 35%, #0f1623 65%, #0a0d14 100%);
  color: var(--text);
}

/* ── 环境光 ── */
.login-ambient {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
  will-change: transform;
}

.orb--1 {
  width: 340px;
  height: 340px;
  top: -100px;
  left: -80px;
  background: rgba(74, 108, 247, 0.22);
  animation: orb-float-1 12s ease-in-out infinite;
}

.orb--2 {
  width: 280px;
  height: 280px;
  top: 42%;
  right: -90px;
  background: rgba(0, 212, 255, 0.14);
  animation: orb-float-2 14s ease-in-out infinite;
}

.orb--3 {
  width: 220px;
  height: 220px;
  bottom: -50px;
  left: 28%;
  background: rgba(212, 163, 115, 0.2);
  animation: orb-float-3 16s ease-in-out infinite;
}

.grid-fade {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.025) 1px, transparent 1px);
  background-size: 64px 64px;
  mask-image: radial-gradient(ellipse 70% 60% at 40% 45%, black 20%, transparent 75%);
  opacity: 0.55;
  animation: grid-breathe 10s ease-in-out infinite;
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
    transform: translate(0, 0) scale(1);
  }
  25% {
    transform: translate(-25px, 10px) scale(1.08);
  }
  50% {
    transform: translate(10px, -15px) scale(0.93);
  }
  75% {
    transform: translate(25px, 5px) scale(1.04);
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

@keyframes grid-breathe {
  0%,
  100% {
    opacity: 0.4;
  }
  50% {
    opacity: 0.65;
  }
}

/* ── 主体分栏 ── */
.login-shell {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
  min-height: 100vh;
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 40px 48px;
  gap: 32px;
  align-items: center;
}

/* ── 品牌区 ── */
.brand-panel {
  position: relative;
  padding: 24px 16px 24px 8px;
  animation: rise-in 0.8s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.brand-panel__glow {
  position: absolute;
  top: -8%;
  left: 10%;
  width: 420px;
  height: 280px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(212, 163, 115, 0.16) 0%, transparent 70%);
  pointer-events: none;
  filter: blur(10px);
}

.brand-content {
  position: relative;
  max-width: 520px;
}

.brand-mark {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 28px;
}

.brand-logo {
  width: 76px;
  height: 76px;
  flex-shrink: 0;
  animation: logo-pulse 4.5s ease-in-out infinite;
  filter: drop-shadow(0 0 18px rgba(212, 163, 115, 0.25));
}

.brand-logo svg {
  width: 100%;
  height: 100%;
}

.logo-ring {
  transform-origin: 40px 40px;
  animation: ring-spin 18s linear infinite;
}

@keyframes logo-pulse {
  0%,
  100% {
    transform: scale(1);
    filter: drop-shadow(0 0 14px rgba(212, 163, 115, 0.2));
  }
  50% {
    transform: scale(1.04);
    filter: drop-shadow(0 0 28px rgba(212, 163, 115, 0.38));
  }
}

@keyframes ring-spin {
  to {
    stroke-dasharray: 40 180;
    stroke-dashoffset: -220;
  }
}

.brand-name {
  margin: 0;
  font-size: clamp(36px, 5vw, 52px);
  font-weight: 800;
  letter-spacing: -1px;
  line-height: 1.1;
  background: linear-gradient(135deg, #f8fafc 0%, #d4a373 52%, #faedcd 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.brand-tagline {
  margin: 0 0 14px;
  font-size: clamp(17px, 2.2vw, 21px);
  font-weight: 500;
  color: #e2e8f0;
  line-height: 1.55;
  animation: rise-in 0.85s cubic-bezier(0.22, 1, 0.36, 1) 0.1s both;
}

.brand-support {
  margin: 0 0 28px;
  max-width: 460px;
  font-size: 14.5px;
  line-height: 1.75;
  color: var(--muted);
  padding-bottom: 18px;
  border-bottom: 1px solid transparent;
  border-image: linear-gradient(90deg, transparent 0%, #d4a373 45%, transparent 100%) 1;
  animation: rise-in 0.85s cubic-bezier(0.22, 1, 0.36, 1) 0.18s both;
}

/* 路径视觉 */
.path-visual {
  margin-bottom: 28px;
  animation: rise-in 0.9s cubic-bezier(0.22, 1, 0.36, 1) 0.26s both;
}

.path-svg {
  width: 100%;
  max-width: 380px;
  height: auto;
  display: block;
}

.path-line {
  fill: none;
  stroke-dasharray: 420;
  stroke-dashoffset: 420;
  animation: draw-path 2.8s ease forwards 0.5s;
}

.path-line--b {
  animation-delay: 0.85s;
  animation-duration: 3.2s;
}

.path-node {
  opacity: 0;
  animation: node-pop 0.5s ease forwards;
}

.path-node--1 {
  animation-delay: 0.7s;
}

.path-node--2 {
  animation-delay: 1.4s;
}

.path-node--3 {
  animation-delay: 2.1s;
  filter: drop-shadow(0 0 8px rgba(0, 212, 255, 0.7));
}

.path-labels {
  display: flex;
  justify-content: space-between;
  max-width: 380px;
  margin-top: 6px;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: none;
  color: var(--dim);
}

@keyframes draw-path {
  to {
    stroke-dashoffset: 0;
  }
}

@keyframes node-pop {
  from {
    opacity: 0;
    transform: scale(0.4);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.brand-pillars {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
}

.brand-pillars li {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--muted);
  animation: rise-in 0.7s cubic-bezier(0.22, 1, 0.36, 1) both;
  animation-delay: calc(0.35s + var(--i) * 0.08s);
}

.pillar-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--oat);
  box-shadow: 0 0 10px rgba(212, 163, 115, 0.55);
}

/* ── 表单区 ── */
.form-panel {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  animation: rise-in 0.9s cubic-bezier(0.22, 1, 0.36, 1) 0.15s both;
}

.form-card {
  position: relative;
  width: 100%;
  max-width: 420px;
  margin-left: auto;
  padding: 36px 32px 28px;
  border-radius: 20px;
  background: linear-gradient(165deg, rgba(255, 255, 255, 0.06) 0%, rgba(255, 255, 255, 0.025) 100%);
  border: 1px solid rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(22px) saturate(1.2);
  -webkit-backdrop-filter: blur(22px) saturate(1.2);
  box-shadow:
    0 20px 60px rgba(0, 0, 0, 0.35),
    0 0 0 1px rgba(212, 163, 115, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.form-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 12%;
  right: 12%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(212, 163, 115, 0.55), transparent);
}

.form-header {
  margin-bottom: 28px;
}

.form-eyebrow {
  margin: 0 0 8px;
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--oat);
  opacity: 0.85;
}

.form-title {
  margin: 0 0 8px;
  font-size: 26px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.3px;
}

.form-subtitle {
  margin: 0;
  font-size: 13.5px;
  color: var(--muted);
  line-height: 1.5;
}

.login-form :deep(.ant-form-item) {
  margin-bottom: 18px;
}

.login-form :deep(.login-input.ant-input-affix-wrapper),
.login-form :deep(.login-input.ant-input-password) {
  background: rgba(10, 13, 20, 0.55) !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  border-radius: 12px !important;
  padding: 10px 14px !important;
  box-shadow: none !important;
  transition:
    border-color 0.25s ease,
    box-shadow 0.25s ease,
    background 0.25s ease;
}

.login-form :deep(.login-input.ant-input-affix-wrapper:hover),
.login-form :deep(.login-input.ant-input-password:hover) {
  border-color: rgba(212, 163, 115, 0.35) !important;
  background: rgba(10, 13, 20, 0.7) !important;
}

.login-form :deep(.login-input.ant-input-affix-wrapper-focused),
.login-form :deep(.login-input.ant-input-password-focused),
.login-form :deep(.login-input.ant-input-affix-wrapper:focus-within) {
  border-color: rgba(212, 163, 115, 0.65) !important;
  box-shadow: 0 0 0 3px rgba(212, 163, 115, 0.12) !important;
  background: rgba(10, 13, 20, 0.78) !important;
}

.login-form :deep(.ant-input) {
  background: transparent !important;
  color: var(--text) !important;
}

.login-form :deep(.ant-input::placeholder) {
  color: var(--dim) !important;
}

.input-icon {
  color: var(--dim);
}

.form-extra {
  display: flex;
  align-items: center;
  margin: -4px 0 20px;
}

.form-extra :deep(.ant-checkbox-wrapper) {
  color: var(--muted);
  font-size: 13px;
}

.form-extra :deep(.ant-checkbox-inner) {
  background: rgba(10, 13, 20, 0.6);
  border-color: rgba(255, 255, 255, 0.2);
}

.form-extra :deep(.ant-checkbox-checked .ant-checkbox-inner) {
  background: var(--oat);
  border-color: var(--oat);
}

.submit-item {
  margin-bottom: 8px !important;
}

.login-btn {
  position: relative;
  width: 100%;
  height: 48px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: 0.28em;
  color: #0a0d14;
  background: linear-gradient(135deg, #faedcd 0%, #d4a373 55%, #c08b5c 100%);
  box-shadow:
    0 8px 24px rgba(212, 163, 115, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.35);
  transition:
    transform 0.25s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.25s ease,
    filter 0.25s ease;
  overflow: hidden;
}

.login-btn::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(110deg, transparent 30%, rgba(255, 255, 255, 0.28) 50%, transparent 70%);
  transform: translateX(-120%);
  transition: transform 0.6s ease;
}

.login-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow:
    0 12px 32px rgba(212, 163, 115, 0.38),
    0 0 40px rgba(212, 163, 115, 0.12);
}

.login-btn:hover:not(:disabled)::after {
  transform: translateX(120%);
}

.login-btn:active:not(:disabled) {
  transform: translateY(0);
}

.login-btn:disabled {
  cursor: wait;
  opacity: 0.85;
}

.login-btn__arrow {
  font-size: 14px;
  letter-spacing: 0;
  transition: transform 0.25s ease;
}

.login-btn:hover:not(:disabled) .login-btn__arrow {
  transform: translateX(3px);
}

.login-btn__spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(10, 13, 20, 0.25);
  border-top-color: #0a0d14;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Demo */
.demo-section {
  margin-top: 8px;
}

.demo-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  color: var(--dim);
  font-size: 12px;
}

.demo-divider::before,
.demo-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
}

.demo-buttons {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.demo-btn {
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  background: rgba(255, 255, 255, 0.03);
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    transform 0.2s ease;
}

.demo-btn--student {
  border: 1px solid rgba(52, 211, 153, 0.35);
  color: #34d399;
}

.demo-btn--student:hover {
  background: rgba(52, 211, 153, 0.1);
  border-color: #34d399;
  transform: translateY(-1px);
}

.demo-btn--teacher {
  border: 1px solid rgba(251, 191, 36, 0.35);
  color: #fbbf24;
}

.demo-btn--teacher:hover {
  background: rgba(212, 163, 115, 0.1);
  border-color: var(--oat);
  color: var(--oat);
  transform: translateY(-1px);
}

.form-footer {
  margin-top: 22px;
  text-align: center;
  font-size: 13px;
  color: var(--dim);
}

.link-btn {
  margin-left: 4px;
  padding: 0;
  border: none;
  background: none;
  color: var(--oat);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: color 0.2s ease;
}

.link-btn:hover {
  color: var(--oat-soft);
}

.form-credit {
  margin: 18px 0 0 auto;
  max-width: 420px;
  text-align: center;
  font-size: 11px;
  letter-spacing: 0.14em;
  color: rgba(100, 116, 139, 0.7);
}

@keyframes rise-in {
  from {
    opacity: 0;
    transform: translateY(18px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ── 响应式 ── */
@media (max-width: 960px) {
  .login-shell {
    grid-template-columns: 1fr;
    padding: 32px 24px 40px;
    gap: 20px;
    align-content: center;
  }

  .brand-panel {
    padding: 8px 0 0;
    text-align: center;
  }

  .brand-mark {
    justify-content: center;
  }

  .brand-support {
    margin-left: auto;
    margin-right: auto;
  }

  .path-visual {
    display: none;
  }

  .brand-pillars {
    justify-content: center;
  }

  .form-card {
    margin: 0 auto;
  }

  .form-credit {
    margin-left: auto;
    margin-right: auto;
  }
}

@media (max-width: 480px) {
  .login-shell {
    padding: 24px 16px 32px;
  }

  .brand-logo {
    width: 56px;
    height: 56px;
  }

  .brand-name {
    font-size: 32px;
  }

  .brand-tagline {
    font-size: 16px;
  }

  .brand-support {
    font-size: 13px;
  }

  .form-card {
    padding: 28px 20px 22px;
    border-radius: 16px;
  }

  .demo-buttons {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .orb,
  .grid-fade,
  .brand-logo,
  .logo-ring,
  .path-line,
  .path-node,
  .brand-panel,
  .form-panel,
  .brand-tagline,
  .brand-support,
  .path-visual,
  .brand-pillars li {
    animation: none !important;
  }

  .path-line {
    stroke-dashoffset: 0;
  }

  .path-node {
    opacity: 1;
  }

  .login-btn::after {
    display: none;
  }
}
</style>
