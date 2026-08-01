<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import type { LoginParams } from '@/types'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

// ========== 表单 ==========
const formRef = ref<FormInstance>()
const loading = ref(false)

const formState = reactive<LoginParams>({
  username: '',
  password: '',
  remember: true
})

// ========== 表单验证规则 ==========
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

// ========== 登录 ==========
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
      // 登录成功 → 跳转到 redirect 页面或首页
      const redirect = (route.query['redirect'] as string) || '/home'
      router.push(redirect)
    }
  } finally {
    loading.value = false
  }
}

// ========== 模拟 Demo 登录 ==========
function demoLogin(role: 'student' | 'teacher') {
  formState.username = role === 'student' ? 'student_demo' : 'teacher_demo'
  formState.password = '123456'
  handleLogin()
}
</script>

<template>
  <div class="login-page">
    <!-- 左侧品牌区 -->
    <div class="login-banner">
      <div class="banner-overlay"></div>
      <div class="banner-content">
        <div class="banner-logo">
          <div class="banner-logo-icon">
            <BulbOutlined />
          </div>
          <h1 class="banner-title">燕麦智导</h1>
        </div>
        <p class="banner-desc">智能化学习路径规划平台，让每一位学习者找到最适合自己的成长路径</p>
        <div class="banner-features">
          <div class="feature-item">
            <CheckCircleOutlined class="feature-icon" />
            <span>AI 认知诊断</span>
          </div>
          <div class="feature-item">
            <CheckCircleOutlined class="feature-icon" />
            <span>个性化路径推荐</span>
          </div>
          <div class="feature-item">
            <CheckCircleOutlined class="feature-icon" />
            <span>智能学科问答</span>
          </div>
          <div class="feature-item">
            <CheckCircleOutlined class="feature-icon" />
            <span>学情数据可视化</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧登录表单 -->
    <div class="login-form-area">
      <div class="form-container">
        <div class="form-header">
          <h2 class="form-title">欢迎回来</h2>
          <p class="form-subtitle">登录您的账号继续学习</p>
        </div>

        <a-form
          ref="formRef"
          :model="formState"
          :rules="rules"
          layout="vertical"
          size="large"
          @finish="handleLogin"
        >
          <a-form-item name="username">
            <a-input
              v-model:value="formState.username"
              placeholder="请输入用户名"
              autocomplete="username"
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
            >
              <template #prefix>
                <LockOutlined class="input-icon" />
              </template>
            </a-input-password>
          </a-form-item>

          <div class="form-extra">
            <a-checkbox v-model:checked="formState.remember">记住登录状态</a-checkbox>
          </div>

          <a-form-item>
            <a-button type="primary" html-type="submit" :loading="loading" block class="login-btn">
              登 录
            </a-button>
          </a-form-item>
        </a-form>

        <!-- Demo 快速登录 -->
        <div class="demo-section">
          <div class="demo-divider">
            <span>快速体验</span>
          </div>
          <div class="demo-buttons">
            <a-button class="demo-btn student" @click="demoLogin('student')">
              <UserOutlined />
              学生 Demo
            </a-button>
            <a-button class="demo-btn teacher" @click="demoLogin('teacher')">
              <TeamOutlined />
              教师 Demo
            </a-button>
          </div>
        </div>

        <div class="form-footer">
          还没有账号？
          <a-button type="link" size="small" @click="router.push('/register')"> 立即注册 </a-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import {
  BulbOutlined,
  UserOutlined,
  LockOutlined,
  CheckCircleOutlined,
  TeamOutlined
} from '@ant-design/icons-vue'

export default {
  components: {
    BulbOutlined,
    UserOutlined,
    LockOutlined,
    CheckCircleOutlined,
    TeamOutlined
  }
}
</script>

<style scoped>
/* ============================================================
   页面布局
   ============================================================ */
.login-page {
  display: flex;
  min-height: 100vh;
  overflow: hidden;
}

/* ============================================================
   左侧品牌区
   ============================================================ */
.login-banner {
  flex: 1;
  position: relative;
  background: linear-gradient(135deg, #141b2b 0%, #0f1623 50%, #0a0d14 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-right: 1px solid rgba(212, 163, 115, 0.08);
}

.banner-overlay {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 30% 40%, rgba(212, 163, 115, 0.08) 0%, transparent 50%),
    radial-gradient(circle at 70% 60%, rgba(0, 212, 255, 0.06) 0%, transparent 40%);
}

.banner-content {
  position: relative;
  z-index: 1;
  max-width: 420px;
  padding: 60px 40px;
  color: #f8fafc;
}

.banner-logo {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.banner-logo-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(212, 163, 115, 0.25), rgba(212, 163, 115, 0.08));
  border: 1px solid rgba(212, 163, 115, 0.2);
  border-radius: 16px;
  font-size: 28px;
  color: #d4a373;
}

.banner-title {
  font-size: 32px;
  font-weight: 700;
  margin: 0;
  letter-spacing: 2px;
}

.banner-desc {
  font-size: 15px;
  line-height: 1.7;
  opacity: 0.75;
  color: #94a3b8;
  margin-bottom: 36px;
}

.banner-features {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: #94a3b8;
  opacity: 0.85;
}

.feature-icon {
  font-size: 16px;
  color: #d4a373;
}

/* ============================================================
   右侧表单区
   ============================================================ */
.login-form-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  padding: 40px;
}

.form-container {
  width: 100%;
  max-width: 400px;
}

.form-header {
  margin-bottom: 32px;
}

.form-title {
  font-size: 26px;
  font-weight: 700;
  color: #f8fafc;
  margin: 0 0 8px 0;
}

.form-subtitle {
  color: #94a3b8;
  font-size: 14px;
  margin: 0;
}

.input-icon {
  color: #64748b;
}

.form-extra {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  margin-top: -8px;
}

.login-btn {
  height: 44px;
  font-size: 15px;
  font-weight: 600;
  border-radius: 8px;
  letter-spacing: 4px;
}

/* Demo */
.demo-section {
  margin-top: 24px;
}

.demo-divider {
  display: flex;
  align-items: center;
  color: #64748b;
  font-size: 12px;
  margin-bottom: 16px;
}

.demo-divider::before,
.demo-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: rgba(255, 255, 255, 0.08);
}

.demo-divider span {
  padding: 0 16px;
}

.demo-buttons {
  display: flex;
  gap: 12px;
}

.demo-btn {
  flex: 1;
  border-radius: 8px;
  height: 38px;
  font-size: 13px;
  font-weight: 500;
}

.demo-btn.student {
  border-color: rgba(52, 211, 153, 0.35);
  color: #34d399;
  background: rgba(255, 255, 255, 0.03);
}

.demo-btn.student:hover {
  border-color: #34d399;
  color: #34d399;
  background: rgba(52, 211, 153, 0.08);
}

.demo-btn.teacher {
  border-color: rgba(251, 191, 36, 0.35);
  color: #fbbf24;
  background: rgba(255, 255, 255, 0.03);
}

.demo-btn.teacher:hover {
  border-color: #d4a373;
  color: #d4a373;
  background: rgba(212, 163, 115, 0.08);
}

.form-footer {
  margin-top: 24px;
  text-align: center;
  font-size: 13px;
  color: #64748b;
}

/* ============================================================
   响应式
   ============================================================ */
@media (max-width: 768px) {
  .login-banner {
    display: none;
  }
}
</style>
