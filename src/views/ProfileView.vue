<script setup lang="ts">
/**
 * 个人中心 — 个人信息 / 账号设置
 *
 * 说明：
 * - 「个人信息」展示当前登录账号的真实资料（来源 GET /auth/me），
 *   昵称 / 邮箱 / 手机号 / 头像支持本地与服务器同步保存。
 * - 「账号设置」为客户端偏好设置，保存在 localStorage，
 *   不涉及服务端状态，刷新与重新登录后依旧保留。
 */
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { useUserStore } from '@/stores/user'
import { useAppStore } from '@/stores/app'
import {
  IdcardOutlined,
  SettingOutlined,
  UserOutlined,
  MailOutlined,
  PhoneOutlined,
  SafetyCertificateOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
  SaveOutlined,
  LogoutOutlined,
  CameraOutlined,
  InfoCircleOutlined
} from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const appStore = useAppStore()

// ═══════════ 头像上传 ═══════════

const avatarInputRef = ref<HTMLInputElement | null>(null)
const uploadingAvatar = ref(false)

function triggerAvatarUpload() {
  avatarInputRef.value?.click()
}

function onAvatarSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (!file.type.startsWith('image/')) {
    message.warning('请选择图片文件')
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    message.warning('头像图片不能超过 2MB')
    return
  }
  uploadingAvatar.value = true
  const reader = new FileReader()
  reader.onload = async () => {
    const dataUrl = reader.result as string
    // 立即写入本地，保证 UI 即时生效
    userStore.updateUserInfo({ avatar: dataUrl })
    // 尝试同步到服务端
    const ok = await userStore.syncProfileToServer({ avatar: dataUrl })
    uploadingAvatar.value = false
    message.success(ok ? '头像已保存至服务器' : '头像已保存至本机（服务器同步失败）')
  }
  reader.onerror = () => {
    uploadingAvatar.value = false
    message.error('头像读取失败，请重试')
  }
  reader.readAsDataURL(file)
}

/** 优先展示已上传头像，否则回退到昵称首字符 */
const avatarSrc = computed(() => userStore.userInfo?.avatar || '')


// ═══════════ Tab ═══════════

const activeTab = ref<'profile' | 'settings'>(
  route.query['tab'] === 'settings' ? 'settings' : 'profile'
)

// URL 上的 tab 参数变化时同步（下拉菜单在本页内再次点击时也能切换）
watch(
  () => route.query['tab'],
  (t) => {
    activeTab.value = t === 'settings' ? 'settings' : 'profile'
  }
)

// Tab 切换时回写 URL，便于刷新 / 分享保持在同一分页
watch(activeTab, (t) => {
  if (route.query['tab'] !== t) {
    router.replace({ path: '/profile', query: { tab: t } })
  }
})

// ═══════════ 个人信息 ═══════════

const infoLoading = ref(false)
const saving = ref(false)

const form = reactive({
  nickname: '',
  email: '',
  phone: ''
})

/** 用上一次拉取到的用户信息填充表单 */
function resetForm() {
  const u = userStore.userInfo
  form.nickname = u?.nickname ?? ''
  form.email = u?.email ?? ''
  form.phone = u?.phone ?? ''
}

async function refreshUserInfo() {
  infoLoading.value = true
  try {
    await userStore.fetchUserInfo()
    resetForm()
  } finally {
    infoLoading.value = false
  }
}

const roleText = computed(() => (userStore.isTeacher ? '教师' : '学生'))

const statusText = computed(() =>
  userStore.userInfo?.status === 1 ? '正常' : '已停用'
)

const createTimeText = computed(() => {
  const t = userStore.userInfo?.createTime
  if (!t) return '—'
  const d = new Date(t)
  return Number.isNaN(d.getTime()) ? t : d.toLocaleString('zh-CN', { hour12: false })
})

/** 昵称首字符，用作头像占位 */
const avatarChar = computed(() => {
  const name = userStore.displayName
  return name && name !== '未登录' ? name.trim().charAt(0).toUpperCase() : ''
})

const emailInvalid = computed(
  () => !!form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)
)

const phoneInvalid = computed(() => !!form.phone && !/^1[3-9]\d{9}$/.test(form.phone))

const dirty = computed(() => {
  const u = userStore.userInfo
  return (
    form.nickname !== (u?.nickname ?? '') ||
    form.email !== (u?.email ?? '') ||
    form.phone !== (u?.phone ?? '')
  )
})

async function handleSaveProfile() {
  if (!form.nickname.trim()) {
    message.warning('昵称不能为空')
    return
  }
  if (emailInvalid.value) {
    message.warning('邮箱格式不正确')
    return
  }
  if (phoneInvalid.value) {
    message.warning('手机号格式不正确')
    return
  }

  saving.value = true
  try {
    const profile = {
      nickname: form.nickname.trim(),
      email: form.email.trim(),
      phone: form.phone.trim()
    }
    // 先写入本地，保证即时生效
    userStore.updateUserInfo(profile)
    // 尝试同步到服务端
    const ok = await userStore.syncProfileToServer(profile)
    message.success(ok ? '资料已保存至服务器' : '资料已保存至本机（服务器同步失败）')
  } finally {
    saving.value = false
  }
}

// ═══════════ 账号设置（本地偏好） ═══════════

const PREF_KEY = 'oat_preferences'

interface Preferences {
  /** 侧边栏默认折叠 */
  siderCollapsed: boolean
  /** 页面切换动画 */
  pageTransition: boolean
  /** 图表动画 */
  chartAnimation: boolean
  /** 诊断答题自动进入下一题 */
  autoNextQuestion: boolean
  /** 问答流式输出 */
  chatStream: boolean
  /** 操作成功提示 */
  successToast: boolean
}

const defaultPrefs: Preferences = {
  siderCollapsed: false,
  pageTransition: true,
  chartAnimation: true,
  autoNextQuestion: true,
  chatStream: true,
  successToast: true
}

const prefs = reactive<Preferences>({ ...defaultPrefs })

function loadPrefs() {
  try {
    const raw = localStorage.getItem(PREF_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as Partial<Preferences>
    ;(Object.keys(defaultPrefs) as Array<keyof Preferences>).forEach((k) => {
      if (typeof parsed[k] === 'boolean') prefs[k] = parsed[k] as boolean
    })
  } catch {
    // 解析失败时沿用默认值，不打断页面
  }
}

function persistPrefs() {
  try {
    localStorage.setItem(PREF_KEY, JSON.stringify({ ...prefs }))
  } catch {
    message.error('本机存储不可用，设置未能保存')
  }
}

function onPrefChange() {
  persistPrefs()
  // 侧边栏折叠可即时反映
  if (appStore.collapsed !== prefs.siderCollapsed) {
    appStore.collapsed = prefs.siderCollapsed
  }
}

function resetPrefs() {
  Object.assign(prefs, defaultPrefs)
  persistPrefs()
  message.success('已恢复默认设置')
}

// ═══════════ 危险操作 ═══════════

function clearLocalCache() {
  Modal.confirm({
    title: '清除本机缓存',
    content: '将清除本机保存的诊断快照、路径草稿与界面偏好，不会影响服务器上的数据。',
    okText: '确认清除',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => {
      const keep = ['oat_user_store']
      Object.keys(localStorage)
        .filter((k) => k.startsWith('oat_') && !keep.includes(k))
        .forEach((k) => localStorage.removeItem(k))
      Object.assign(prefs, defaultPrefs)
      message.success('本机缓存已清除')
    }
  })
}

function handleLogout() {
  Modal.confirm({
    title: '确认退出',
    content: '确定要退出登录吗？',
    okText: '确定',
    cancelText: '取消',
    onOk: () => {
      userStore.logout(false)
      window.location.replace('/login')
    }
  })
}

onMounted(() => {
  resetForm()
  loadPrefs()
  prefs.siderCollapsed = appStore.collapsed
  // 静默刷新一次，保证展示的是服务端最新资料
  refreshUserInfo()
})
</script>

<template>
  <div class="profile-page">
    <div class="page-head">
      <h2 class="page-title">个人中心</h2>
      <p class="page-desc">查看你的账号资料，并管理本机的使用偏好。</p>
    </div>

    <a-tabs v-model:activeKey="activeTab" class="profile-tabs">
      <!-- ══════════ 个人信息 ══════════ -->
      <a-tab-pane key="profile">
        <template #tab>
          <span class="tab-label"><IdcardOutlined /> 个人信息</span>
        </template>

        <a-spin :spinning="infoLoading">
          <div class="profile-grid">
            <!-- 名片 -->
            <section class="panel identity-card">
              <div
                class="identity-avatar"
                :class="{ clickable: true, uploading: uploadingAvatar }"
                title="点击更换头像"
                @click="triggerAvatarUpload"
              >
                <img v-if="avatarSrc" :src="avatarSrc" alt="头像" class="identity-avatar-img" />
                <span v-else-if="avatarChar">{{ avatarChar }}</span>
                <UserOutlined v-else />
                <span class="avatar-camera"><CameraOutlined /></span>
                <input
                  ref="avatarInputRef"
                  type="file"
                  accept="image/*"
                  class="avatar-input"
                  @change="onAvatarSelected"
                />
              </div>
              <div class="identity-name">{{ userStore.displayName }}</div>
              <div class="identity-account">@{{ userStore.userInfo?.username || '—' }}</div>
              <div class="identity-badges">
                <span class="badge" :class="userStore.role || 'student'">{{ roleText }}</span>
                <span class="badge status" :class="{ off: userStore.userInfo?.status !== 1 }">
                  {{ statusText }}
                </span>
              </div>
              <a-button
                class="refresh-btn"
                size="small"
                :loading="infoLoading"
                @click="refreshUserInfo"
              >
                <template #icon><ReloadOutlined /></template>
                刷新资料
              </a-button>
            </section>

            <!-- 资料明细 + 编辑 -->
            <section class="panel detail-card">
              <header class="panel-head">
                <h3 class="panel-title">账号资料</h3>
                <span class="panel-hint">带 * 的字段可编辑</span>
              </header>

              <div class="field-list">
                <div class="field readonly">
                  <label class="field-label"><UserOutlined /> 用户名</label>
                  <div class="field-value">{{ userStore.userInfo?.username || '—' }}</div>
                </div>

                <div class="field readonly">
                  <label class="field-label"><SafetyCertificateOutlined /> 账号角色</label>
                  <div class="field-value">{{ roleText }}</div>
                </div>

                <div class="field readonly">
                  <label class="field-label"><ClockCircleOutlined /> 注册时间</label>
                  <div class="field-value">{{ createTimeText }}</div>
                </div>

                <div class="field">
                  <label class="field-label"><IdcardOutlined /> 昵称 *</label>
                  <a-input
                    class="profile-input"
                    v-model:value="form.nickname"
                    placeholder="请输入昵称"
                    :maxlength="24"
                    allow-clear
                  />
                </div>

                <div class="field">
                  <label class="field-label"><MailOutlined /> 邮箱 *</label>
                  <a-input
                    class="profile-input"
                    v-model:value="form.email"
                    placeholder="用于接收学习报告，可留空"
                    :status="emailInvalid ? 'error' : ''"
                    allow-clear
                  />
                  <div v-if="emailInvalid" class="field-error">邮箱格式不正确</div>
                </div>

                <div class="field">
                  <label class="field-label"><PhoneOutlined /> 手机号 *</label>
                  <a-input
                    class="profile-input"
                    v-model:value="form.phone"
                    placeholder="11 位手机号，可留空"
                    :status="phoneInvalid ? 'error' : ''"
                    allow-clear
                  />
                  <div v-if="phoneInvalid" class="field-error">手机号格式不正确</div>
                </div>
              </div>

              <div class="panel-foot">
                <div class="save-note">
                  <InfoCircleOutlined class="save-note-icon" />
                  <span class="save-note-text">修改后将自动同步至服务器，同时保存在本机，刷新页面后依然生效。</span>
                </div>
                <div class="foot-actions">
                  <a-button :disabled="!dirty" @click="resetForm">撤销修改</a-button>
                  <a-button type="primary" :disabled="!dirty" :loading="saving" @click="handleSaveProfile">
                    <template #icon><SaveOutlined /></template>
                    保存修改
                  </a-button>
                </div>
              </div>
            </section>
          </div>
        </a-spin>
      </a-tab-pane>

      <!-- ══════════ 账号设置 ══════════ -->
      <a-tab-pane key="settings">
        <template #tab>
          <span class="tab-label"><SettingOutlined /> 账号设置</span>
        </template>

        <div class="settings-grid">
          <section class="panel">
            <header class="panel-head">
              <h3 class="panel-title">界面偏好</h3>
              <span class="panel-hint">保存在本机</span>
            </header>

            <div class="switch-list">
              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">默认折叠侧边栏</div>
                  <div class="switch-desc">进入页面时侧边栏保持收起，主内容区更宽敞</div>
                </div>
                <a-switch v-model:checked="prefs.siderCollapsed" @change="onPrefChange" />
              </div>

              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">页面切换动画</div>
                  <div class="switch-desc">切换菜单时的淡入淡出过渡效果</div>
                </div>
                <a-switch v-model:checked="prefs.pageTransition" @change="onPrefChange" />
              </div>

              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">图表动画</div>
                  <div class="switch-desc">关闭后雷达图、甘特图等将直接渲染，低配设备更流畅</div>
                </div>
                <a-switch v-model:checked="prefs.chartAnimation" @change="onPrefChange" />
              </div>
            </div>
          </section>

          <section class="panel">
            <header class="panel-head">
              <h3 class="panel-title">学习偏好</h3>
              <span class="panel-hint">保存在本机</span>
            </header>

            <div class="switch-list">
              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">答题后自动进入下一题</div>
                  <div class="switch-desc">认知诊断中选择答案后自动跳转，关闭则需手动点击</div>
                </div>
                <a-switch v-model:checked="prefs.autoNextQuestion" @change="onPrefChange" />
              </div>

              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">问答流式输出</div>
                  <div class="switch-desc">智能问答逐字返回答案，关闭则等待完整回复后一次展示</div>
                </div>
                <a-switch v-model:checked="prefs.chatStream" @change="onPrefChange" />
              </div>

              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">操作成功提示</div>
                  <div class="switch-desc">保存、删除等操作完成后弹出轻提示</div>
                </div>
                <a-switch v-model:checked="prefs.successToast" @change="onPrefChange" />
              </div>
            </div>

            <div class="panel-foot">
              <div class="foot-actions">
                <a-button @click="resetPrefs">
                  <template #icon><ReloadOutlined /></template>
                  恢复默认设置
                </a-button>
              </div>
            </div>
          </section>

          <section class="panel danger-panel">
            <header class="panel-head">
              <h3 class="panel-title">账号与数据</h3>
              <span class="panel-hint danger">请谨慎操作</span>
            </header>

            <div class="switch-list">
              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">清除本机缓存</div>
                  <div class="switch-desc">
                    清空本机保存的诊断快照与界面偏好，服务器上的记录不受影响
                  </div>
                </div>
                <a-button danger ghost @click="clearLocalCache">清除</a-button>
              </div>

              <div class="switch-row">
                <div class="switch-text">
                  <div class="switch-title">退出登录</div>
                  <div class="switch-desc">退出当前账号并返回登录页</div>
                </div>
                <a-button danger @click="handleLogout">
                  <template #icon><LogoutOutlined /></template>
                  退出
                </a-button>
              </div>
            </div>
          </section>
        </div>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<style scoped>
.profile-page {
  padding: 8px 4px 24px;
}

/* ── 页头 ── */
.page-head {
  margin-bottom: 8px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: #f8fafc;
  letter-spacing: 0.5px;
}

.page-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: #94a3b8;
}

/* ── Tabs ── */
.profile-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 20px;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

/* ── 通用面板 ── */
.panel {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 14px;
  padding: 20px;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
}

.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #f1f5f9;
}

.panel-hint {
  font-size: 12px;
  color: #94a3b8;
}

.panel-hint.danger {
  color: #f4a1a1;
}

.panel-foot {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
}

.foot-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* ── 个人信息布局 ── */
.profile-grid {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 20px;
  align-items: start;
}

.identity-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 28px 20px;
}

.identity-avatar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 82px;
  height: 82px;
  border-radius: 50%;
  font-size: 32px;
  font-weight: 700;
  color: #0f1623;
  background: linear-gradient(135deg, #d4a373, #e8c39e);
  box-shadow: 0 8px 24px rgba(212, 163, 115, 0.28);
  margin-bottom: 14px;
  overflow: hidden;
  transition: box-shadow 0.25s ease;
}

.identity-avatar.clickable {
  cursor: pointer;
}

.identity-avatar.clickable:hover {
  box-shadow: 0 8px 28px rgba(74, 108, 247, 0.4);
}

.identity-avatar.uploading {
  opacity: 0.7;
  pointer-events: none;
}

.identity-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-camera {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  color: #fff;
  background: rgba(15, 22, 35, 0.55);
  opacity: 0;
  transition: opacity 0.2s ease;
}

.identity-avatar.clickable:hover .avatar-camera {
  opacity: 1;
}

.avatar-input {
  display: none;
}

.identity-name {
  font-size: 18px;
  font-weight: 700;
  color: #f8fafc;
}

.identity-account {
  margin-top: 4px;
  font-size: 13px;
  color: #94a3b8;
  font-family: 'JetBrains Mono', monospace;
}

.identity-badges {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}

.badge {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 10px;
  font-weight: 600;
}

.badge.teacher {
  background: rgba(251, 191, 36, 0.18);
  color: #fbbf24;
  border: 1px solid rgba(251, 191, 36, 0.28);
}

.badge.student {
  background: rgba(52, 211, 153, 0.18);
  color: #34d399;
  border: 1px solid rgba(52, 211, 153, 0.28);
}

.badge.status {
  background: rgba(74, 108, 247, 0.18);
  color: #8fa9ff;
  border: 1px solid rgba(74, 108, 247, 0.3);
}

.badge.status.off {
  background: rgba(248, 113, 113, 0.16);
  color: #fca5a5;
  border-color: rgba(248, 113, 113, 0.3);
}

.refresh-btn {
  margin-top: 18px;
}

/* ── 字段列表 ── */
.field-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 20px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.field-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  letter-spacing: 0.3px;
}

.field-value {
  min-height: 32px;
  display: flex;
  align-items: center;
  padding: 0 11px;
  font-size: 14px;
  color: #e2e8f0;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  word-break: break-all;
}

/* 可编辑输入框与只读框 (.field-value) 配色对齐, 消除默认边框带来的"双层颜色" */
.profile-input :deep(.ant-input),
.profile-input :deep(.ant-input-affix-wrapper) {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
  color: #e2e8f0;
}

.profile-input :deep(.ant-input::placeholder) {
  color: #64748b;
}

.profile-input :deep(.ant-input):hover,
.profile-input :deep(.ant-input-affix-wrapper):hover {
  border-color: rgba(255, 255, 255, 0.18);
}

.profile-input :deep(.ant-input):focus,
.profile-input :deep(.ant-input-focused),
.profile-input :deep(.ant-input-affix-wrapper-focused),
.profile-input :deep(.ant-input-affix-wrapper):focus {
  border-color: #D4A373;
  box-shadow: 0 0 0 2px rgba(212, 163, 115, 0.15);
}

/* 校验错误态沿用系统错误红, 不破坏既有提示语义 */
.profile-input :deep(.ant-input-status-error),
.profile-input :deep(.ant-input-affix-wrapper-status-error) {
  background: rgba(255, 255, 255, 0.04);
  border-color: #fca5a5;
}

.field-error {
  font-size: 12px;
  color: #fca5a5;
}

.save-note {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  background: rgba(30, 41, 59, 0.9);
  border: 1px solid rgba(74, 108, 247, 0.4);
  border-left: 4px solid #4a6cf7;
  border-radius: 8px;
  margin-bottom: 14px;
}

.save-note-icon {
  font-size: 16px;
  color: #4a6cf7;
  flex-shrink: 0;
  margin-top: 1px;
}

.save-note-text {
  font-size: 13px;
  color: #e2e8f0;
  line-height: 1.6;
}

/* ── 设置布局 ── */
.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 20px;
  align-items: start;
}

.switch-list {
  display: flex;
  flex-direction: column;
}

.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 14px 0;
  border-bottom: 1px dashed rgba(255, 255, 255, 0.07);
}

.switch-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.switch-row:first-child {
  padding-top: 0;
}

.switch-text {
  min-width: 0;
}

.switch-title {
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
}

.switch-desc {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.6;
  color: #94a3b8;
}

.danger-panel {
  border-color: rgba(248, 113, 113, 0.22);
  background: rgba(248, 113, 113, 0.04);
}

/* ── 响应式 ── */
@media (max-width: 900px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }

  .field-list {
    grid-template-columns: 1fr;
  }
}
</style>
