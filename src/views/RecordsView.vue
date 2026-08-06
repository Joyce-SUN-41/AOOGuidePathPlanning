<script setup lang="ts">
/**
 * 我的记录 — 测绘历史与学习路径的查看 / 删除
 * 数据来自真实持久化存储，统计侧边栏点击数字可带 query.tab 进入对应分页。
 */
import { ref, onMounted } from 'vue'
import { useIsMobile } from '@/composables/useIsMobile'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { cehuiApi } from '@/api/modules/cehui'
import { pathApi } from '@/api/modules/path'
import { useCehuiStore } from '@/stores/cehui'
import { usePathStore } from '@/stores/path'
import eventBus from '@/utils/eventBus'
import type { CehuiBrief, CehuiResult, LearningPath } from '@/types'

// 移动端断点
const { isMobile } = useIsMobile()

const route = useRoute()
const router = useRouter()
const cehuiStore = useCehuiStore()
const pathStore = usePathStore()

// 当前激活的 Tab: 侧边栏可能带 ?tab=cehui|path 进入
const activeTab = ref<'cehui' | 'path'>(
  route.query['tab'] === 'path' ? 'path' : 'cehui'
)

// ── 测绘记录 ──
const diagLoading = ref(false)
const diagList = ref<CehuiBrief[]>([])
const diagTotal = ref(0)
const diagPage = ref(1)
const diagPageSize = ref(10)

async function loadCehuis() {
  diagLoading.value = true
  try {
    const res = await cehuiApi.getHistory({
      page: diagPage.value,
      pageSize: diagPageSize.value,
    })
    diagList.value = res.list
    diagTotal.value = res.total
  } catch (e) {
    message.error('加载测绘记录失败')
  } finally {
    diagLoading.value = false
  }
}

function onDiagTableChange(pag: { current?: number }) {
  diagPage.value = pag.current ?? 1
  loadCehuis()
}

// 测绘详情弹窗
const diagDetailVisible = ref(false)
const diagDetailLoading = ref(false)
const diagDetail = ref<CehuiResult | null>(null)

async function viewCehui(id: string) {
  diagDetailVisible.value = true
  diagDetailLoading.value = true
  diagDetail.value = null
  try {
    diagDetail.value = await cehuiApi.getById(id)
  } catch (e) {
    message.error('获取测绘详情失败')
  } finally {
    diagDetailLoading.value = false
  }
}

async function deleteCehui(id: string) {
  try {
    await cehuiApi.delete(id)
    message.success('测绘记录已删除')

    // 被删除的若是当前正在展示的测绘，需要清掉持久化的陈旧快照，
    // 否则「学情看板」会继续渲染已不存在的数据。
    if (cehuiStore.currentCehui?.id === id) {
      cehuiStore.clear()
    }

    await loadCehuis()
    // 同步刷新最新测绘 + 通知侧边栏统计
    await cehuiStore.fetchLatestCehui()
    eventBus.emit('cehui:changed')
  } catch (e) {
    message.error('删除失败')
  }
}

// ── 学习路径 ──
const pathLoading = ref(false)
const pathList = ref<LearningPath[]>([])

async function loadPaths() {
  pathLoading.value = true
  try {
    pathList.value = await pathApi.getHistory()
  } catch (e) {
    message.error('加载学习路径失败')
  } finally {
    pathLoading.value = false
  }
}

const pathDetailVisible = ref(false)
const pathDetail = ref<LearningPath | null>(null)

function viewPath(p: LearningPath) {
  pathDetail.value = p
  pathDetailVisible.value = true
}

function openPathInApp(p: LearningPath) {
  router.push({ path: '/path', query: { id: p.id } })
}

async function deletePath(id: string) {
  try {
    await pathApi.deletePath(id)
    message.success('学习路径已删除')

    // 清理持久化的当前路径快照，避免「学习路径」页残留已删除的数据
    if (pathStore.currentPath?.id === id) {
      pathStore.clearPath()
    }

    await loadPaths()
    eventBus.emit('path:changed')
  } catch (e) {
    message.error('删除失败')
  }
}

const subjectText = (s: string) =>
  ({ math: '数学', physics: '物理', chemistry: '化学', biology: '生物', english: '英语' } as Record<string, string>)[s] || s

const fmtDate = (d?: string) =>
  d ? new Date(d).toLocaleString('zh-CN', { hour12: false }) : '-'

onMounted(() => {
  loadCehuis()
  loadPaths()
})
</script>

<template>
  <div class="records-page">
    <a-typography-title :level="3">我的记录</a-typography-title>
    <a-typography-paragraph type="secondary">
      这里汇总你历次「学情测绘」与生成的「学习路径」，可随时查看详情或删除。
    </a-typography-paragraph>

    <a-tabs v-model:activeKey="activeTab">
      <!-- ── 测绘记录 ── -->
      <a-tab-pane key="cehui" tab="测绘记录">
        <a-table
          :dataSource="diagList"
          :scroll="{ x: 'max-content' }"
          :loading="diagLoading"
          :pagination="{
            current: diagPage,
            pageSize: diagPageSize,
            total: diagTotal,
            showSizeChanger: false,
          }"
          :rowKey="(r: CehuiBrief) => r.id"
          size="middle"
          @change="onDiagTableChange"
        >
          <a-table-column key="subject" title="学科" align="center" :width="120">
            <template #default="{ record }">{{ subjectText(record.subject) }}</template>
          </a-table-column>
          <a-table-column key="createdAt" title="测绘时间" align="center" :width="200">
            <template #default="{ record }">{{ fmtDate(record.createdAt) }}</template>
          </a-table-column>
          <a-table-column key="overallScore" title="综合得分" align="center" :width="120">
            <template #default="{ record }">
              <a-tag :color="record.overallScore >= 80 ? 'green' : record.overallScore >= 60 ? 'orange' : 'red'">
                {{ record.overallScore }}
              </a-tag>
            </template>
          </a-table-column>
          <a-table-column key="weakPointCount" title="薄弱点" align="center" :width="100">
            <template #default="{ record }">{{ record.weakPointCount }} 项</template>
          </a-table-column>
          <a-table-column key="action" title="操作" align="center" :width="180">
            <template #default="{ record }">
              <a-space>
                <a-button type="link" size="small" @click="viewCehui(record.id)">查看</a-button>
                <a-popconfirm title="确认删除该测绘记录？" @confirm="deleteCehui(record.id)">
                  <a-button type="link" size="small" danger>删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table-column>
          <template #emptyText>
            <span>还没有测绘记录，去「学情测绘」完成一次测验吧</span>
          </template>
        </a-table>
      </a-tab-pane>

      <!-- ── 学习路径 ── -->
      <a-tab-pane key="path" tab="学习路径">
        <a-table
          :dataSource="pathList"
          :scroll="{ x: 'max-content' }"
          :loading="pathLoading"
          :pagination="false"
          :rowKey="(r: LearningPath) => r.id"
          size="middle"
        >
          <a-table-column key="taskId" title="任务 ID" align="center" :width="260">
            <template #default="{ record }">{{ record.taskId }}</template>
          </a-table-column>
          <a-table-column key="totalDays" title="总天数" align="center" :width="100">
            <template #default="{ record }">{{ record.totalDays }} 天</template>
          </a-table-column>
          <a-table-column key="totalTasks" title="任务数" align="center" :width="100">
            <template #default="{ record }">{{ record.totalTasks }} 个</template>
          </a-table-column>
          <a-table-column key="createdAt" title="生成时间" align="center" :width="200">
            <template #default="{ record }">{{ fmtDate(record.createdAt) }}</template>
          </a-table-column>
          <a-table-column key="action" title="操作" align="center" :width="200">
            <template #default="{ record }">
              <a-space>
                <a-button type="link" size="small" @click="viewPath(record)">查看</a-button>
                <a-button type="link" size="small" @click="openPathInApp(record)">打开</a-button>
                <a-popconfirm title="确认删除该学习路径？" @confirm="deletePath(record.id)">
                  <a-button type="link" size="small" danger>删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table-column>
          <template #emptyText>
            <span>还没有学习路径，完成测绘后将自动生成</span>
          </template>
        </a-table>
      </a-tab-pane>
    </a-tabs>

    <!-- 测绘详情弹窗 -->
    <a-modal
      v-model:open="diagDetailVisible"
      title="测绘详情"
      :width="isMobile ? '90%' : 720"
      :footer="null"
    >
      <a-spin :spinning="diagDetailLoading">
        <template v-if="diagDetail">
          <a-descriptions bordered :column="2" size="small">
            <a-descriptions-item label="学科">{{ subjectText(diagDetail.subject) }}</a-descriptions-item>
            <a-descriptions-item label="年级">{{ diagDetail.grade }}</a-descriptions-item>
            <a-descriptions-item label="综合得分">
              <a-tag :color="diagDetail.overallScore >= 80 ? 'green' : diagDetail.overallScore >= 60 ? 'orange' : 'red'">
                {{ diagDetail.overallScore }}
              </a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="认知负荷">{{ diagDetail.cognitiveLoad }}</a-descriptions-item>
          </a-descriptions>

          <a-divider orientation="left">AI 测绘摘要</a-divider>
          <p>{{ diagDetail.summary }}</p>

          <a-divider orientation="left">薄弱知识点 ({{ diagDetail.weakPoints.length }})</a-divider>
          <a-list size="small" :dataSource="diagDetail.weakPoints" :split="false">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-tag color="red">{{ item.knowledgePoint }}</a-tag>
                <span type="secondary">严重度：{{ item.severity }}</span>
              </a-list-item>
            </template>
          </a-list>
        </template>
      </a-spin>
    </a-modal>

    <!-- 路径详情弹窗 -->
    <a-modal
      v-model:open="pathDetailVisible"
      title="学习路径详情"
      :width="isMobile ? '90%' : 640"
      :footer="null"
    >
      <template v-if="pathDetail">
        <a-descriptions bordered :column="2" size="small">
          <a-descriptions-item label="任务 ID">{{ pathDetail.taskId }}</a-descriptions-item>
          <a-descriptions-item label="总天数">{{ pathDetail.totalDays }}</a-descriptions-item>
          <a-descriptions-item label="任务数">{{ pathDetail.totalTasks }}</a-descriptions-item>
          <a-descriptions-item label="生成时间">{{ fmtDate(pathDetail.createdAt) }}</a-descriptions-item>
        </a-descriptions>
        <a-divider orientation="left">路径数据概览</a-divider>
        <a-typography-paragraph type="secondary">
          共 {{ pathDetail.dailyTasks?.length || 0 }} 个每日任务单元，难度曲线已生成。
          点击「打开」可在「我的路径」中查看完整日程与寻优回放。
        </a-typography-paragraph>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.records-page {
  padding: 8px 4px;
}

/* 表格分页器居中 */
.records-page :deep(.ant-pagination) {
  text-align: center;
  display: flex;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
}
</style>
