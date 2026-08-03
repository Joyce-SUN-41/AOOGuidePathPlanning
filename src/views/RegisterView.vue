<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import type { RegisterParams } from '@/types'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

// ========== 表单 ==========
const formRef = ref<FormInstance>()
const loading = ref(false)

const formState = reactive<RegisterParams>({
  username: '',
  password: '',
  confirmPassword: '',
  nickname: '',
  email: '',
  role: 'student'
})

// ========== 密码一致性验证 ==========
const validateConfirmPassword = async (_rule: Rule, value: string) => {
  if (!value) {
    return Promise.reject(new Error('请再次输入密码'))
  }
  if (value !== formState.password) {
    return Promise.reject(new Error('两次输入的密码不一致'))
  }
  return Promise.resolve()
}

// ========== 表单验证规则 ==========
const rules: Record<string, Rule[]> = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 20, message: '用户名长度 2-20 个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 20, message: '密码长度 6-20 个字符', trigger: 'blur' }
  ],
  confirmPassword: [{ required: true, validator: validateConfirmPassword, trigger: 'blur' }],
  nickname: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { max: 20, message: '昵称不能超过 20 个字符', trigger: 'blur' }
  ],
  email: [{ type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }]
}

// ========== 注册 ==========
async function handleRegister() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  loading.value = true
  try {
    const success = await userStore.register(formState)
    if (success) {
      const redirect = (route.query['redirect'] as string) || '/home'
      router.push(redirect)
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="register-page">
    <div class="register-container">
      <!-- 头部 -->
      <div class="register-header">
        <div class="header-logo" @click="router.push('/login')">
          <div class="logo-icon">
            <BulbOutlined />
          </div>
          <span class="logo-text">燕麦智导</span>
        </div>
        <h2 class="register-title">创建账号</h2>
        <p class="register-subtitle">加入燕麦智导，开启智能学习之旅</p>
      </div>

      <!-- 表单 -->
      <a-form
        ref="formRef"
        :model="formState"
        :rules="rules"
        layout="vertical"
        size="large"
        class="register-form"
        @finish="handleRegister"
      >
        <a-row :gutter="16">
          <a-col :xs="24" :span="12">
            <a-form-item name="username">
              <a-input
                v-model:value="formState.username"
                placeholder="用户名"
                autocomplete="username"
              >
                <template #prefix>
                  <UserOutlined class="input-icon" />
                </template>
              </a-input>
            </a-form-item>
          </a-col>
          <a-col :xs="24" :span="12">
            <a-form-item name="nickname">
              <a-input v-model:value="formState.nickname" placeholder="昵称（显示名称）">
                <template #prefix>
                  <IdcardOutlined class="input-icon" />
                </template>
              </a-input>
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item name="email">
          <a-input v-model:value="formState.email" placeholder="邮箱（选填）" autocomplete="email">
            <template #prefix>
              <MailOutlined class="input-icon" />
            </template>
          </a-input>
        </a-form-item>

        <a-form-item name="role">
          <a-radio-group v-model:value="formState.role" button-style="solid" class="role-group">
            <a-radio-button value="student">
              <UserOutlined />
              我是学生
            </a-radio-button>
            <a-radio-button value="teacher">
              <TeamOutlined />
              我是教师
            </a-radio-button>
          </a-radio-group>
        </a-form-item>

        <a-form-item name="password">
          <a-input-password
            v-model:value="formState.password"
            placeholder="密码（6-20 个字符）"
            autocomplete="new-password"
          >
            <template #prefix>
              <LockOutlined class="input-icon" />
            </template>
          </a-input-password>
        </a-form-item>

        <a-form-item name="confirmPassword">
          <a-input-password
            v-model:value="formState.confirmPassword"
            placeholder="确认密码"
            autocomplete="new-password"
          >
            <template #prefix>
              <LockOutlined class="input-icon" />
            </template>
          </a-input-password>
        </a-form-item>

        <a-form-item>
          <a-button type="primary" html-type="submit" :loading="loading" block class="register-btn">
            注 册
          </a-button>
        </a-form-item>
      </a-form>

      <div class="register-footer">
        已有账号？
        <a-button type="link" size="small" @click="router.push('/login')"> 立即登录 </a-button>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import {
  BulbOutlined,
  UserOutlined,
  LockOutlined,
  IdcardOutlined,
  MailOutlined,
  TeamOutlined
} from '@ant-design/icons-vue'

export default {
  components: {
    BulbOutlined,
    UserOutlined,
    LockOutlined,
    IdcardOutlined,
    MailOutlined,
    TeamOutlined
  }
}
</script>

<style scoped>
/* ============================================================
   页面布局
   ============================================================ */
.register-page {
  min-height: 100vh;
  background: radial-gradient(ellipse at 50% 30%, #141b2b 0%, #0f1623 50%, #0a0d14 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.register-container {
  width: 100%;
  max-width: 480px;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: 16px;
  padding: 48px 40px 36px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

/* ============================================================
   头部
   ============================================================ */
.register-header {
  text-align: center;
  margin-bottom: 36px;
}

.header-logo {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  margin-bottom: 20px;
}

.logo-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, #d4a373, #b8860b);
  border-radius: 12px;
  font-size: 22px;
  color: #0a0d14;
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: #f8fafc;
  letter-spacing: 1px;
}

.register-title {
  font-size: 24px;
  font-weight: 700;
  color: #f8fafc;
  margin: 0 0 8px;
}

.register-subtitle {
  color: #94a3b8;
  font-size: 14px;
  margin: 0;
}

/* ============================================================
   表单
   ============================================================ */
.register-form {
  margin-top: 8px;
}

.input-icon {
  color: #94a3b8;
}

.role-group {
  width: 100%;
}

.role-group :deep(.ant-radio-button-wrapper) {
  width: 50%;
  text-align: center;
  height: 42px;
  line-height: 42px;
  border-radius: 8px !important;
}

.role-group :deep(.ant-radio-button-wrapper:first-child) {
  border-radius: 8px 0 0 8px !important;
}

.role-group :deep(.ant-radio-button-wrapper:last-child) {
  border-radius: 0 8px 8px 0 !important;
}

.register-btn {
  height: 44px;
  font-size: 15px;
  font-weight: 600;
  border-radius: 8px;
  letter-spacing: 4px;
  margin-top: 8px;
}

/* ============================================================
   底部
   ============================================================ */
.register-footer {
  text-align: center;
  font-size: 13px;
  color: #94a3b8;
  margin-top: 16px;
}

/* ============================================================
   响应式适配（平板 / 手机 / 小屏手机 + 刘海安全区）
   ============================================================ */
.register-page {
  /* 适配 iOS 刘海 / 手势条安全区 */
  padding: calc(40px + env(safe-area-inset-top)) calc(40px + env(safe-area-inset-right))
    calc(40px + env(safe-area-inset-bottom)) calc(40px + env(safe-area-inset-left));
}

@media (max-width: 768px) {
  .register-page {
    padding: 24px 16px;
    padding-top: calc(24px + env(safe-area-inset-top));
    padding-bottom: calc(24px + env(safe-area-inset-bottom));
    align-items: flex-start;
  }

  .register-container {
    padding: 32px 24px 24px;
    border-radius: 12px;
    /* 移动端关闭毛玻璃以提升渲染性能与兼容性 */
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }

  .register-title {
    font-size: 22px;
  }
}

@media (max-width: 480px) {
  .register-page {
    padding: 16px 12px;
    padding-top: calc(16px + env(safe-area-inset-top));
    padding-bottom: calc(16px + env(safe-area-inset-bottom));
  }

  .register-container {
    padding: 28px 18px 20px;
  }

  .register-header {
    margin-bottom: 24px;
  }

  .register-title {
    font-size: 20px;
  }

  .register-subtitle {
    font-size: 13px;
  }
}
</style>
