<script setup lang="ts">
import { ref } from 'vue'

/** 技术栈列表 */
const techStack = ref([
  { name: 'Vue 3', version: '3.4', description: '渐进式 JavaScript 框架', icon: 'https://cn.vuejs.org/logo.svg' },
  { name: 'Vite', version: '5.3', description: '下一代前端构建工具', icon: 'https://vitejs.dev/logo.svg' },
  { name: 'TypeScript', version: '5.5', description: 'JavaScript 的超集', icon: '' },
  { name: 'Pinia', version: '2.1', description: 'Vue 状态管理', icon: '' },
  { name: 'Ant Design Vue', version: '4.2', description: '企业级 UI 组件库', icon: '' },
  { name: 'ECharts', version: '5.5', description: '数据可视化图表库', icon: '' },
  { name: 'Vue Router', version: '4.4', description: 'Vue 官方路由', icon: '' },
  { name: 'Axios', version: '1.7', description: 'HTTP 请求库', icon: '' },
  { name: 'VueUse', version: '10.11', description: '组合式工具集', icon: '' }
])
</script>

<template>
  <div class="about-page">
    <a-typography>
      <a-typography-title :level="3">
        <info-circle-outlined style="margin-right: 8px" />
        关于项目
      </a-typography-title>
      <a-typography-paragraph>
        这是一个基于 <a-typography-text strong>Vue3</a-typography-text> +
        <a-typography-text strong>Vite</a-typography-text> +
        <a-typography-text strong>TypeScript</a-typography-text>
        构建的前端项目脚手架，集成了企业级开发所需的常用工具和库。
      </a-typography-paragraph>
    </a-typography>

    <a-divider />

    <!-- 技术栈 -->
    <a-typography-title :level="4">
      技术栈一览
    </a-typography-title>

    <a-row :gutter="[16, 16]">
      <a-col
        v-for="tech in techStack"
        :key="tech.name"
        :xs="24"
        :sm="12"
        :md="8"
        :lg="8"
      >
        <a-card :bordered="false" class="tech-card">
          <a-card-meta>
            <template #title>
              <a-space>
                <a-tag color="blue">{{ tech.name }}</a-tag>
                <a-tag>{{ tech.version }}</a-tag>
              </a-space>
            </template>
            <template #description>
              {{ tech.description }}
            </template>
          </a-card-meta>
        </a-card>
      </a-col>
    </a-row>

    <a-divider />

    <!-- 项目结构 -->
    <a-typography-title :level="4">
      项目结构
    </a-typography-title>

    <a-card :bordered="false">
      <a-tree
        :tree-data="treeData"
        default-expand-all
        :show-line="true"
        :show-icon="true"
      >
        <template #icon="{ dataRef }">
          <FolderOutlined v-if="dataRef?.isDir" style="color: #faad14" />
          <FileOutlined v-else style="color: #1677ff" />
        </template>
      </a-tree>
    </a-card>
  </div>
</template>

<script lang="ts">
import { InfoCircleOutlined, FolderOutlined, FileOutlined } from '@ant-design/icons-vue'

export default {
  components: {
    InfoCircleOutlined,
    FolderOutlined,
    FileOutlined
  },
  data() {
    return {
      treeData: [
        {
          title: 'src/',
          key: 'src',
          isDir: true,
          children: [
            { title: 'api/', key: 'api', isDir: true, children: [
              { title: 'index.ts (Axios封装)', key: 'api-index', isDir: false },
              { title: 'modules/', key: 'api-modules', isDir: true, children: [
                { title: 'user.ts (用户API)', key: 'api-user', isDir: false }
              ]}
            ]},
            { title: 'assets/', key: 'assets', isDir: true },
            { title: 'components/', key: 'components', isDir: true, children: [
              { title: 'GlobalLoading.vue', key: 'comp-loading', isDir: false }
            ]},
            { title: 'composables/', key: 'composables', isDir: true, children: [
              { title: 'useECharts.ts', key: 'comp-echarts', isDir: false }
            ]},
            { title: 'layouts/', key: 'layouts', isDir: true, children: [
              { title: 'DefaultLayout.vue', key: 'layout-default', isDir: false }
            ]},
            { title: 'router/', key: 'router', isDir: true, children: [
              { title: 'index.ts (路由配置)', key: 'router-index', isDir: false }
            ]},
            { title: 'stores/', key: 'stores', isDir: true, children: [
              { title: 'app.ts (全局状态)', key: 'store-app', isDir: false },
              { title: 'counter.ts (计数器)', key: 'store-counter', isDir: false }
            ]},
            { title: 'types/', key: 'types', isDir: true, children: [
              { title: 'index.ts (类型定义)', key: 'types-index', isDir: false }
            ]},
            { title: 'utils/', key: 'utils', isDir: true, children: [
              { title: 'index.ts (工具函数)', key: 'utils-index', isDir: false }
            ]},
            { title: 'views/', key: 'views', isDir: true, children: [
              { title: 'HomeView.vue', key: 'view-home', isDir: false },
              { title: 'AboutView.vue', key: 'view-about', isDir: false },
              { title: 'NotFoundView.vue', key: 'view-404', isDir: false }
            ]},
            { title: 'App.vue', key: 'app', isDir: false },
            { title: 'main.ts', key: 'main', isDir: false }
          ]
        }
      ]
    }
  }
}
</script>

<style scoped>
.about-page {
  max-width: 1200px;
  margin: 0 auto;
}

.tech-card {
  height: 100%;
  border-radius: 8px;
  transition: box-shadow 0.3s ease;
}

.tech-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}
</style>
