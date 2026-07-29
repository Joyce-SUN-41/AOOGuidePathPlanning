<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import type { MenuClickEventHandler } from 'ant-design-vue/es/menu/src/interface'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()

/** 当前选中的菜单项 */
const selectedKeys = ref<string[]>([route.path])

/** 菜单项配置 */
const menuItems = [
  { key: '/home', icon: () => h(HomeOutlined), label: '首页' },
  { key: '/about', icon: () => h(InfoCircleOutlined), label: '关于' }
]

/** 面包屑 */
const breadcrumbs = computed(() => {
  const matched = route.matched.filter((item) => item.meta?.title)
  return matched.map((item) => item.meta?.title as string)
})

/** 菜单点击 */
const handleMenuClick: MenuClickEventHandler = ({ key }) => {
  router.push(key as string)
}

// 监听路由变化，更新选中菜单
import { watch } from 'vue'
import { HomeOutlined, InfoCircleOutlined } from '@ant-design/icons-vue'

watch(
  () => route.path,
  (path) => {
    selectedKeys.value = [path]
  }
)
</script>

<template>
  <a-layout style="min-height: 100vh">
    <!-- 侧边栏 -->
    <a-layout-sider
      v-model:collapsed="appStore.collapsed"
      :theme="appStore.theme"
      collapsible
      breakpoint="lg"
    >
      <div class="logo">
        <span v-if="!appStore.collapsed" class="logo-text">
          {{ $t ? 'AOOG' : 'AOOG' }}
        </span>
        <span v-else class="logo-text-mini">AG</span>
      </div>
      <a-menu
        v-model:selectedKeys="selectedKeys"
        :theme="appStore.theme"
        mode="inline"
        :items="menuItems"
        @click="handleMenuClick"
      />
    </a-layout-sider>

    <!-- 右侧主体 -->
    <a-layout>
      <!-- 顶部栏 -->
      <a-layout-header class="header">
        <div class="header-left">
          <menu-unfold-outlined
            v-if="appStore.collapsed"
            class="trigger"
            @click="appStore.toggleCollapsed"
          />
          <menu-fold-outlined
            v-else
            class="trigger"
            @click="appStore.toggleCollapsed"
          />
          <a-breadcrumb class="breadcrumb">
            <a-breadcrumb-item v-for="(item, index) in breadcrumbs" :key="index">
              {{ item }}
            </a-breadcrumb-item>
          </a-breadcrumb>
        </div>
        <div class="header-right">
          <a-space>
            <a-tooltip title="全屏">
              <fullscreen-outlined class="header-icon" />
            </a-tooltip>
            <a-tooltip title="通知">
              <a-badge :count="5">
                <bell-outlined class="header-icon" />
              </a-badge>
            </a-tooltip>
            <a-dropdown>
              <a-avatar style="background-color: #1677ff; cursor: pointer">
                <template #icon><UserOutlined /></template>
              </a-avatar>
              <template #overlay>
                <a-menu>
                  <a-menu-item key="profile">
                    <user-outlined />
                    个人中心
                  </a-menu-item>
                  <a-menu-item key="settings">
                    <setting-outlined />
                    系统设置
                  </a-menu-item>
                  <a-menu-divider />
                  <a-menu-item key="logout">
                    <logout-outlined />
                    退出登录
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </a-space>
        </div>
      </a-layout-header>

      <!-- 内容区域 -->
      <a-layout-content class="content">
        <div class="content-wrapper">
          <router-view v-slot="{ Component }">
            <transition name="fade" mode="out-in">
              <keep-alive>
                <component :is="Component" />
              </keep-alive>
            </transition>
          </router-view>
        </div>
      </a-layout-content>

      <!-- 底部 -->
      <a-layout-footer class="footer">
        AOOGuidePathPlanning &copy; {{ new Date().getFullYear() }}
      </a-layout-footer>
    </a-layout>
  </a-layout>
</template>

<script lang="ts">
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  FullscreenOutlined,
  BellOutlined,
  UserOutlined,
  SettingOutlined,
  LogoutOutlined
} from '@ant-design/icons-vue'

export default {
  components: {
    MenuFoldOutlined,
    MenuUnfoldOutlined,
    FullscreenOutlined,
    BellOutlined,
    UserOutlined,
    SettingOutlined,
    LogoutOutlined
  }
}
</script>

<style scoped>
.logo {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.logo-text {
  color: #fff;
  font-size: 18px;
  font-weight: bold;
  white-space: nowrap;
}

.logo-text-mini {
  color: #fff;
  font-size: 20px;
  font-weight: bold;
}

.header {
  background: #fff;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  z-index: 1;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-right {
  display: flex;
  align-items: center;
}

.trigger {
  font-size: 18px;
  cursor: pointer;
  transition: color 0.3s;
}

.trigger:hover {
  color: #1677ff;
}

.breadcrumb {
  margin-left: 8px;
}

.header-icon {
  font-size: 18px;
  cursor: pointer;
  transition: color 0.3s;
}

.header-icon:hover {
  color: #1677ff;
}

.content {
  margin: 16px;
}

.content-wrapper {
  min-height: calc(100vh - 64px - 69px - 32px);
  background: #fff;
  border-radius: 8px;
  padding: 24px;
}

.footer {
  text-align: center;
  background: #f0f2f5;
  color: #999;
}

/* 页面切换动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
