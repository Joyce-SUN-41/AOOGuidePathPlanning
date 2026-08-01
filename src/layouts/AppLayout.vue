<script setup lang="ts">
import { ref, computed, watch, h, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'
import { dashboardApi } from '@/api/modules/dashboard'
import eventBus from '@/utils/eventBus'
import type { UserRole } from '@/types'
import {
  BulbOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  DownOutlined,
  UserOutlined,
  SettingOutlined,
  LogoutOutlined,
  IdcardOutlined,
  HomeOutlined,
  ExperimentOutlined,
  NodeIndexOutlined,
  RobotOutlined,
  DashboardOutlined,
  TeamOutlined,
  ApartmentOutlined,
  FileTextOutlined,
  HistoryOutlined
} from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const userStore = useUserStore()

// ========== 侧边栏 ==========

/** 图标组件映射（用于侧边栏 <component :is> 渲染） */
const iconComponents: Record<string, any> = {
  HomeOutlined,
  ExperimentOutlined,
  NodeIndexOutlined,
  RobotOutlined,
  DashboardOutlined,
  TeamOutlined,
  ApartmentOutlined,
  FileTextOutlined,
  HistoryOutlined
}

// ========== 顶部菜单 ==========

/** 当前选中的顶级菜单 */
const selectedKeys = ref<string[]>([route.path])

/** 菜单项（根据角色动态过滤）
 *  顶层 a-menu 使用 Ant Design items 属性，icon 需要是 VNode 或渲染函数 */
const menuItems = computed(() => {
  const allItems: Array<{
    key: string
    icon: any
    iconKey: string
    label: string
    roles: UserRole[]
  }> = [
    {
      key: '/home',
      icon: () => h(HomeOutlined),
      iconKey: 'HomeOutlined',
      label: '首页',
      roles: []
    },
    {
      key: '/diagnose',
      icon: () => h(ExperimentOutlined),
      iconKey: 'ExperimentOutlined',
      label: '认知诊断',
      roles: ['student']
    },
    {
      key: '/path',
      icon: () => h(NodeIndexOutlined),
      iconKey: 'NodeIndexOutlined',
      label: '我的路径',
      roles: ['student']
    },
    {
      key: '/chat',
      icon: () => h(RobotOutlined),
      iconKey: 'RobotOutlined',
      label: '智能问答',
      roles: ['student']
    },
    {
      key: '/dashboard',
      icon: () => h(DashboardOutlined),
      iconKey: 'DashboardOutlined',
      label: '学情看板',
      roles: ['student']
    },
    {
      key: '/records',
      icon: () => h(HistoryOutlined),
      iconKey: 'HistoryOutlined',
      label: '我的记录',
      roles: ['student']
    },
    {
      key: '/teacher',
      icon: () => h(TeamOutlined),
      iconKey: 'TeamOutlined',
      label: '教师仪表盘',
      roles: ['teacher']
    },
    {
      key: '/teacher/knowledge',
      icon: () => h(ApartmentOutlined),
      iconKey: 'ApartmentOutlined',
      label: '知识点管理',
      roles: ['teacher']
    },
    {
      key: '/teacher/questions',
      icon: () => h(FileTextOutlined),
      iconKey: 'FileTextOutlined',
      label: '题库管理',
      roles: ['teacher']
    }
  ]

  return allItems.filter((item) => {
    if (item.roles.length === 0) return true
    return userStore.role && item.roles.includes(userStore.role)
  })
})

/** 菜单点击 */
function handleMenuClick({ key }: { key: string }) {
  router.push(key)
}

// 路由变化时同步选中菜单
watch(
  () => route.path,
  (path) => {
    // 匹配当前路由对应的顶级菜单 key (最长匹配优先, 避免 /teacher 覆盖 /teacher/knowledge)
    let bestMatch: (typeof menuItems.value)[0] | undefined
    let bestLen = 0
    for (const item of menuItems.value) {
      if (path.startsWith(item.key) && item.key.length > bestLen) {
        bestMatch = item
        bestLen = item.key.length
      }
    }
    if (bestMatch) {
      selectedKeys.value = [bestMatch.key]
    }
  },
  { immediate: true }
)

// ========== 学习统计(实时) ==========
const totalDiagnoses = ref<number>(0)
const totalPaths = ref<number>(0)

async function loadStats() {
  // 教师端不展示「学习统计」，无需请求学生维度概览接口
  if (userStore.isTeacher) return
  try {
    const data = await dashboardApi.getOverview()
    totalDiagnoses.value = data.totalDiagnoses ?? 0
    totalPaths.value = data.totalPaths ?? 0
  } catch (e) {
    // 统计加载失败不影响布局, 保留上次值
  }
}

// 进入应用即加载; 路由切换(诊断完成/路径生成或删除后)刷新统计
onMounted(loadStats)
watch(
  () => route.path,
  (path) => {
    if (
      path.startsWith('/diagnose') ||
      path.startsWith('/path') ||
      path.startsWith('/records')
    ) {
      loadStats()
    }
  }
)

// 停留在同一页面内删除诊断/路径时不会触发路由变化，
// 这里额外监听全局事件，保证「学习统计」实时刷新。
const unsubscribers: Array<() => void> = []
onMounted(() => {
  unsubscribers.push(
    eventBus.on('stats:refresh', loadStats),
    eventBus.on('diagnosis:changed', loadStats),
    eventBus.on('path:changed', loadStats)
  )
})
onUnmounted(() => {
  unsubscribers.forEach((fn) => fn())
  unsubscribers.length = 0
})

function goToRecords(tab: 'diagnosis' | 'path') {
  router.push({ path: '/records', query: { tab } })
}

// ========== 用户下拉 ==========

function handleUserMenuClick({ key }: { key: string }) {
  if (key === 'logout') {
    handleLogout()
  } else if (key === 'profile') {
    router.push({ path: '/profile', query: { tab: 'profile' } })
  } else if (key === 'settings') {
    router.push({ path: '/profile', query: { tab: 'settings' } })
  }
}

// ========== 退出登录确认 ==========

import { Modal } from 'ant-design-vue'

function handleLogout() {
  Modal.confirm({
    title: '确认退出',
    content: '确定要退出登录吗？',
    okText: '确定',
    cancelText: '取消',
    onOk: () => {
      userStore.logout(false)
      // 使用 window.location.replace 强制跳转，避免 keep-alive / 路由守卫竞态导致的页面残留
      window.location.replace('/login')
    }
  })
}
</script>

<template>
  <a-layout class="app-layout">
    <!-- ========== 顶部导航栏 ========== -->
    <a-layout-header class="top-header">
      <!-- Logo -->
      <div class="header-logo" @click="router.push('/home')">
        <div class="logo-icon">
          <BulbOutlined />
        </div>
        <span class="logo-title">燕麦智导</span>
      </div>

      <!-- 水平导航菜单 -->
      <a-menu
        :selectedKeys="selectedKeys"
        mode="horizontal"
        class="top-menu"
        :items="menuItems"
        @click="handleMenuClick"
      />

      <!-- 右侧：用户信息 -->
      <div class="header-user">
        <a-dropdown :trigger="['click']">
          <div class="user-trigger">
            <a-avatar :size="32" class="user-avatar" :src="userStore.avatar || ''">
              <template #icon><UserOutlined /></template>
            </a-avatar>
            <span class="user-name">{{ userStore.displayName }}</span>
            <span class="user-role-badge" :class="userStore.role">
              {{ userStore.role === 'teacher' ? '教师' : '学生' }}
            </span>
            <DownOutlined class="user-arrow" />
          </div>

          <template #overlay>
            <a-menu @click="handleUserMenuClick">
              <a-menu-item key="profile">
                <IdcardOutlined />
                <span>个人信息</span>
              </a-menu-item>
              <a-menu-item key="settings">
                <SettingOutlined />
                <span>账号设置</span>
              </a-menu-item>
              <a-menu-divider />
              <a-menu-item key="logout" danger>
                <LogoutOutlined />
                <span>退出登录</span>
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </div>

      <!-- 折叠按钮 -->
      <div class="collapse-trigger" @click="appStore.toggleCollapsed">
        <MenuFoldOutlined v-if="!appStore.collapsed" />
        <MenuUnfoldOutlined v-else />
      </div>
    </a-layout-header>

    <a-layout class="layout-body">
      <!-- ========== 侧边栏 ========== -->
      <a-layout-sider
        v-model:collapsed="appStore.collapsed"
        :width="220"
        :collapsed-width="64"
        class="app-sider"
        :trigger="null"
        collapsible
        breakpoint="lg"
      >
        <div class="sider-content">
          <!-- 折叠状态：快捷图标 -->
          <div v-if="appStore.collapsed" class="sider-collapsed-menu">
            <div
              v-for="item in menuItems"
              :key="item.key"
              class="sider-icon-item"
              :class="{ active: selectedKeys[0] === item.key }"
              :title="item.label"
              @click="router.push(item.key)"
            >
              <component :is="iconComponents[item.iconKey]" />
            </div>
          </div>

          <!-- 展开状态：补充信息 -->
          <div v-else class="sider-expanded">
            <div class="sider-section">
              <div class="sider-section-title">快捷入口</div>
              <div class="quick-links">
                <div
                  v-for="item in menuItems"
                  :key="item.key"
                  class="quick-link-item"
                  :class="{ active: selectedKeys[0] === item.key }"
                  @click="router.push(item.key)"
                >
                  <component :is="iconComponents[item.iconKey]" class="link-icon" />
                  <span class="link-label">{{ item.label }}</span>
                </div>
              </div>
            </div>

            <div v-if="!userStore.isTeacher" class="sider-section">
              <div class="sider-section-title">学习统计</div>
              <div class="stat-cards">
                <div class="stat-card" @click="goToRecords('diagnosis')" style="cursor: pointer">
                  <div class="stat-value">{{ totalDiagnoses }}</div>
                  <div class="stat-label">已完成诊断</div>
                </div>
                <div class="stat-card" @click="goToRecords('path')" style="cursor: pointer">
                  <div class="stat-value">{{ totalPaths }}</div>
                  <div class="stat-label">学习路径</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </a-layout-sider>

      <!-- ========== 主内容区 ========== -->
      <a-layout>
        <a-layout-content class="main-content">
          <div class="content-wrapper">
            <router-view v-slot="{ Component }">
              <transition name="page-fade" mode="out-in">
                <keep-alive :max="8">
                  <component :is="Component" />
                </keep-alive>
              </transition>
            </router-view>
          </div>
        </a-layout-content>

        <!-- ========== 底部 ========== -->
        <a-layout-footer class="app-footer">
          <div class="footer-content">
            <span>燕麦智导 &copy; {{ new Date().getFullYear() }} — 智能化学习路径规划平台</span>
          </div>
        </a-layout-footer>
      </a-layout>
    </a-layout>
  </a-layout>
</template>

<style scoped>
/* ============================================================
   整体布局
   ============================================================ */
.app-layout {
  min-height: 100vh;
}

/* ============================================================
   顶部导航栏 — 透明 + 底部发光边框（Mac OS 菜单栏风格）
   ============================================================ */
.top-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  height: 56px;
  padding: 0 24px;
  background: rgba(10, 13, 20, 0.82);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  box-shadow: 0 1px 0 rgba(212, 163, 115, 0.08);
}

/* Logo */
.header-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  flex-shrink: 0;
  margin-right: 32px;
}

.logo-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, rgba(212, 163, 115, 0.25), rgba(212, 163, 115, 0.08));
  border: 1px solid rgba(212, 163, 115, 0.2);
  border-radius: 10px;
  font-size: 20px;
  color: #d4a373;
  animation: logo-pulse 3s ease-in-out infinite;
}

@keyframes logo-pulse {
  0%,
  100% {
    box-shadow: 0 0 8px rgba(212, 163, 115, 0.15);
  }
  50% {
    box-shadow: 0 0 18px rgba(212, 163, 115, 0.3);
  }
}

.logo-title {
  font-size: 18px;
  font-weight: 700;
  color: #f8fafc;
  letter-spacing: 1px;
  white-space: nowrap;
  background: linear-gradient(135deg, #f8fafc, #d4a373);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* 水平菜单 */
.top-menu {
  flex: 1;
  min-width: 0;
  background: transparent !important;
  border-bottom: none !important;
  line-height: 56px;
}

.top-menu :deep(.ant-menu-item) {
  color: #64748b !important;
  border-radius: 6px 6px 0 0;
  margin: 0 4px !important;
  padding: 0 18px !important;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.25s;
}

.top-menu :deep(.ant-menu-item:hover) {
  color: #f8fafc !important;
  background: rgba(255, 255, 255, 0.06) !important;
}

.top-menu :deep(.ant-menu-item-selected) {
  color: #d4a373 !important;
  background: rgba(212, 163, 115, 0.1) !important;
  font-weight: 600;
}

.top-menu :deep(.ant-menu-item-selected::after) {
  display: none !important;
}

/* 用户区域 */
.header-user {
  flex-shrink: 0;
  margin-left: auto;
  margin-right: 16px;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 12px;
  border-radius: 20px;
  transition: background 0.25s;
}

.user-trigger:hover {
  background: rgba(255, 255, 255, 0.06);
}

.user-avatar {
  background: linear-gradient(135deg, rgba(74, 108, 247, 0.3), rgba(0, 212, 255, 0.2));
  flex-shrink: 0;
}

.user-name {
  color: #f8fafc;
  font-size: 14px;
  font-weight: 500;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-role-badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.user-role-badge.teacher {
  background: rgba(251, 191, 36, 0.2);
  color: #fbbf24;
  border: 1px solid rgba(251, 191, 36, 0.25);
}

.user-role-badge.student {
  background: rgba(52, 211, 153, 0.2);
  color: #34d399;
  border: 1px solid rgba(52, 211, 153, 0.25);
}

.user-arrow {
  color: #f8fafc;
  font-size: 10px;
}

/* 折叠按钮 */
.collapse-trigger {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  color: #64748b;
  font-size: 16px;
  cursor: pointer;
  transition: all 0.25s;
}

.collapse-trigger:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #f8fafc;
}

/* ============================================================
   主体区域 (顶部占位)
   ============================================================ */
.layout-body {
  margin-top: 56px;
  min-height: calc(100vh - 56px);
}

/* ============================================================
   侧边栏 — 深色毛玻璃
   ============================================================ */
.app-sider {
  background: rgba(10, 13, 20, 0.6) !important;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  overflow: auto;
  position: sticky;
  top: 56px;
  height: calc(100vh - 56px);
}

.app-sider :deep(.ant-layout-sider-children) {
  height: 100%;
}

.sider-content {
  padding: 16px 12px;
  height: 100%;
}

/* 折叠状态 */
.sider-collapsed-menu {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.sider-icon-item {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  font-size: 18px;
  color: #f8fafc;
  cursor: pointer;
  transition: all 0.2s;
}

.sider-icon-item:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #00d4ff;
}

.sider-icon-item.active {
  background: rgba(212, 163, 115, 0.12);
  color: #d4a373;
}

/* 展开状态 */
.sider-section {
  margin-bottom: 24px;
}

.sider-section-title {
  font-size: 12px;
  font-weight: 600;
  color: #f8fafc;
  text-transform: uppercase;
  letter-spacing: 1px;
  padding: 0 8px;
  margin-bottom: 12px;
}

.quick-links {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.quick-link-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  cursor: pointer;
  color: #64748b;
  font-size: 13px;
  transition: all 0.2s;
}

.quick-link-item:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #f8fafc;
}

.quick-link-item.active {
  background: rgba(212, 163, 115, 0.12);
  color: #d4a373;
  font-weight: 600;
}

.link-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.stat-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-card {
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: #d4a373;
  line-height: 1;
  font-family: 'JetBrains Mono', monospace;
}

.stat-label {
  font-size: 12px;
  color: #f8fafc;
  margin-top: 6px;
}

/* ============================================================
   主内容区
   ============================================================ */
.main-content {
  margin: 0;
  min-height: calc(100vh - 56px - 52px);
  background: transparent;
}

.content-wrapper {
  min-height: calc(100vh - 56px - 52px);
  padding: 20px;
}

/* ============================================================
   底部
   ============================================================ */
.app-footer {
  text-align: center;
  background: transparent;
  padding: 16px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.footer-content {
  color: #f8fafc;
  font-size: 13px;
}

/* ============================================================
   页面切换动画
   ============================================================ */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.2s ease;
}

.page-fade-enter-from,
.page-fade-leave-to {
  opacity: 0;
}

/* ============================================================
   响应式
   ============================================================ */
@media (max-width: 768px) {
  .top-menu {
    display: none;
  }

  .user-name {
    display: none;
  }

  .logo-title {
    display: none;
  }

  .header-logo {
    margin-right: 8px;
  }
}
</style>
