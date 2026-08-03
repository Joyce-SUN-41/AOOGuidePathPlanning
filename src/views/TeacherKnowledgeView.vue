<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { message, Modal } from 'ant-design-vue'
import type { KnowledgePoint, KnowledgePointForm, KnowledgeGraphEdge } from '@/types'
import { knowledgeApi } from '@/api/modules/knowledge'
import { useIsMobile } from '@/composables/useIsMobile'

// 移动端断点
const { isMobile } = useIsMobile()

// ========== 数据状态 ==========
const loading = ref(false)
const knowledgePoints = ref<KnowledgePoint[]>([])
const edges = ref<KnowledgeGraphEdge[]>([])
const viewMode = ref<'list' | 'graph'>('list')
const filterSubject = ref('')
const filterLayer = ref('')

// ========== 编辑对话框 ==========
const modalVisible = ref(false)
const modalTitle = ref('新增知识点')
const isEditing = ref(false)
const editingId = ref('')
const form = reactive<KnowledgePointForm>({
  name: '',
  description: '',
  subject: '人工智能导论',
  difficulty_level: 1,
  layer: '',
  tags: [],
  prerequisites: [],
  parent_id: ''
})
const tagInput = ref('')

// ========== 选项常量 ==========
const layerOptions = ['基础层', '核心层', '进阶层']
const subjectOptions = ['人工智能导论', '数学']

// ========== 方法 ==========
async function loadData() {
  loading.value = true
  try {
    const result = await knowledgeApi.getGraph()
    knowledgePoints.value = result.nodes
    edges.value = result.edges
  } catch (e) {
    message.error('加载知识图谱失败')
  } finally {
    loading.value = false
  }
}

// 筛选后的知识点
const filteredPoints = computed(() => {
  return knowledgePoints.value.filter((kp) => {
    if (filterSubject.value && kp.subject !== filterSubject.value) return false
    if (filterLayer.value && kp.layer !== filterLayer.value) return false
    return true
  })
})

// 获取前置知识点的名称
function getPrereqNames(prereqIds: string[]): string {
  return prereqIds
    .map((id) => knowledgePoints.value.find((k) => k.id === id)?.name || id.substring(0, 8))
    .join(' → ')
}

// 难度标签颜色
function getDifficultyColor(level: number): string {
  const colors: Record<number, string> = { 1: 'green', 2: 'cyan', 3: 'blue', 4: 'orange', 5: 'red' }
  return colors[level] || 'default'
}

// 层级标签
function getLayerColor(layer: string | undefined): string {
  const colors: Record<string, string> = { 基础层: 'green', 核心层: 'blue', 进阶层: 'purple' }
  return colors[layer || ''] || 'default'
}

// 打开新增对话框
function openCreate() {
  isEditing.value = false
  editingId.value = ''
  modalTitle.value = '新增知识点'
  Object.assign(form, {
    name: '',
    description: '',
    subject: '人工智能导论',
    difficulty_level: 1,
    layer: '',
    tags: [],
    prerequisites: [],
    parent_id: ''
  })
  modalVisible.value = true
}

// 打开编辑对话框
function openEdit(kp: KnowledgePoint) {
  isEditing.value = true
  editingId.value = kp.id
  modalTitle.value = `编辑知识点: ${kp.name}`
  Object.assign(form, {
    name: kp.name,
    description: kp.description || '',
    subject: kp.subject,
    difficulty_level: kp.difficulty_level,
    layer: kp.layer || '',
    tags: [...kp.tags],
    prerequisites: [...kp.prerequisites],
    parent_id: kp.parent_id || ''
  })
  modalVisible.value = true
}

// 提交表单
async function handleSubmit() {
  if (!form.name.trim()) {
    message.warning('请输入知识点名称')
    return
  }
  try {
    if (isEditing.value) {
      await knowledgeApi.update(editingId.value, form)
      message.success('知识点更新成功')
    } else {
      await knowledgeApi.create(form)
      message.success('知识点创建成功')
    }
    modalVisible.value = false
    await loadData()
  } catch (e: unknown) {
    const errMsg = e instanceof Error ? e.message : '操作失败'
    message.error(errMsg)
  }
}

// 添加标签
function addTag() {
  const val = tagInput.value.trim()
  if (val && !form.tags.includes(val)) {
    form.tags.push(val)
    tagInput.value = ''
  }
}

// 获取前置知识点可选列表
const availablePrereqs = computed(() => {
  return knowledgePoints.value.filter((kp) => kp.id !== editingId.value)
})

// 确认删除
function handleDelete(kp: KnowledgePoint) {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除知识点 "${kp.name}" 吗？如果有关联题目则无法删除。`,
    okText: '确定删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await knowledgeApi.delete(kp.id)
        message.success('知识点已删除')
        await loadData()
      } catch (e: unknown) {
        const errMsg = e instanceof Error ? e.message : '删除失败'
        message.error(errMsg)
      }
    }
  })
}

// ========== 生命周期 ==========
onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="kp-manage-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <div>
        <h1 class="page-title">知识点管理</h1>
        <p class="page-subtitle">管理知识图谱中的知识点节点与前置依赖关系</p>
      </div>
      <div class="header-actions">
        <a-radio-group v-model:value="viewMode" button-style="solid" size="small">
          <a-radio-button value="list">列表视图</a-radio-button>
          <a-radio-button value="graph">图谱视图</a-radio-button>
        </a-radio-group>
        <a-button type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新增知识点
        </a-button>
      </div>
    </div>

    <!-- ========== 筛选工具栏 ========== -->
    <div class="filter-bar">
      <a-space>
        <a-select
          v-model:value="filterSubject"
          placeholder="学科筛选"
          style="width: 160px"
          allow-clear
          :options="subjectOptions.map((s) => ({ value: s, label: s }))"
        />
        <a-select
          v-model:value="filterLayer"
          placeholder="层级筛选"
          style="width: 140px"
          allow-clear
          :options="layerOptions.map((l) => ({ value: l, label: l }))"
        />
        <a-tag color="blue">共 {{ filteredPoints.length }} 个知识点</a-tag>
      </a-space>
    </div>

    <a-spin :spinning="loading">
      <!-- ========== 列表视图 ========== -->
      <div v-if="viewMode === 'list'" class="kp-list">
        <a-table :data-source="filteredPoints" :scroll="{ x: 'max-content' }" :pagination="false" row-key="id" size="middle">
          <a-table-column title="名称" data-index="name" :width="200">
            <template #default="{ record }">
              <span class="kp-name">{{ record.name }}</span>
            </template>
          </a-table-column>
          <a-table-column title="学科" data-index="subject" :width="120">
            <template #default="{ record }">
              <a-tag>{{ record.subject }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="层级" data-index="layer" :width="100">
            <template #default="{ record }">
              <a-tag v-if="record.layer" :color="getLayerColor(record.layer)">{{
                record.layer
              }}</a-tag>
              <span v-else class="text-muted">—</span>
            </template>
          </a-table-column>
          <a-table-column title="难度" data-index="difficulty_level" :width="100">
            <template #default="{ record }">
              <a-tag :color="getDifficultyColor(record.difficulty_level)">
                Lv{{ record.difficulty_level }}
              </a-tag>
            </template>
          </a-table-column>
          <a-table-column title="标签" data-index="tags" :width="160">
            <template #default="{ record }">
              <a-space v-if="record.tags?.length" :size="4" wrap>
                <a-tag v-for="tag in record.tags" :key="tag" color="geekblue" size="small">{{
                  tag
                }}</a-tag>
              </a-space>
              <span v-else class="text-muted">—</span>
            </template>
          </a-table-column>
          <a-table-column title="前置依赖" :width="250">
            <template #default="{ record }">
              <span v-if="record.prerequisites?.length" class="prereq-text">
                {{ getPrereqNames(record.prerequisites) }}
              </span>
              <span v-else class="text-muted">无</span>
            </template>
          </a-table-column>
          <a-table-column title="操作" :width="160" align="center" fixed="right">
            <template #default="{ record }">
              <a-space>
                <a-button type="link" size="small" @click="openEdit(record)">编辑</a-button>
                <a-button type="link" danger size="small" @click="handleDelete(record)"
                  >删除</a-button
                >
              </a-space>
            </template>
          </a-table-column>
        </a-table>
      </div>

      <!-- ========== 图谱视图 ========== -->
      <div v-else class="kp-graph-view">
        <div class="graph-container">
          <!-- 按层级分组显示 -->
          <div v-for="layer in layerOptions" :key="layer" class="graph-layer">
            <div class="layer-header">
              <a-tag :color="getLayerColor(layer)" class="layer-tag">{{ layer }}</a-tag>
            </div>
            <div class="layer-nodes">
              <div
                v-for="kp in filteredPoints.filter((p) => p.layer === layer)"
                :key="kp.id"
                class="graph-node-card"
              >
                <div class="node-header">
                  <span class="node-name">{{ kp.name }}</span>
                  <a-tag :color="getDifficultyColor(kp.difficulty_level)" size="small">
                    Lv{{ kp.difficulty_level }}
                  </a-tag>
                </div>
                <div class="node-desc">{{ kp.description || '暂无描述' }}</div>
                <div v-if="kp.prerequisites?.length" class="node-prereqs">
                  <span class="prereq-label">前置: </span>
                  <span class="prereq-list">{{ getPrereqNames(kp.prerequisites) }}</span>
                </div>
                <div class="node-actions">
                  <a-button type="link" size="small" @click="openEdit(kp)">编辑</a-button>
                  <a-button type="link" danger size="small" @click="handleDelete(kp)"
                    >删除</a-button
                  >
                </div>
              </div>
              <div
                v-if="filteredPoints.filter((p) => p.layer === layer).length === 0"
                class="empty-nodes"
              >
                暂无该层级的知识点
              </div>
            </div>
          </div>

          <!-- 图谱连线图例 -->
          <div class="graph-legend">
            <span class="legend-title">依赖关系 ({{ edges.length }} 条):</span>
            <div class="legend-edges">
              <span v-for="edge in edges.slice(0, 8)" :key="edge.id" class="legend-edge">
                {{ edge.source_name }} → {{ edge.target_name }}
              </span>
              <span v-if="edges.length > 8" class="legend-more"
                >...还有 {{ edges.length - 8 }} 条</span
              >
            </div>
          </div>
        </div>
      </div>
    </a-spin>

    <!-- ========== 新增/编辑对话框 ========== -->
    <a-modal
      v-model:open="modalVisible"
      :title="modalTitle"
      :width="isMobile ? '90%' : 640"
      @ok="handleSubmit"
      ok-text="保存"
      cancel-text="取消"
      :destroy-on-close="true"
    >
      <a-form layout="vertical" class="kp-form">
        <a-row :gutter="16">
          <a-col :span="16">
            <a-form-item label="知识点名称" required>
              <a-input v-model:value="form.name" placeholder="如: 机器学习基础" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="难度等级" required>
              <a-input-number
                v-model:value="form.difficulty_level"
                :min="1"
                :max="5"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="学科">
              <a-select
                v-model:value="form.subject"
                :options="subjectOptions.map((s) => ({ value: s, label: s }))"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="层级">
              <a-select
                v-model:value="form.layer"
                :options="layerOptions.map((l) => ({ value: l, label: l }))"
                placeholder="选择层级"
                allow-clear
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="描述">
          <a-textarea v-model:value="form.description" :rows="3" placeholder="知识点描述..." />
        </a-form-item>

        <a-form-item label="标签">
          <a-space>
            <a-input
              v-model:value="tagInput"
              placeholder="输入标签后回车"
              style="width: 160px"
              @press-enter="addTag"
            />
            <a-button size="small" @click="addTag">添加</a-button>
          </a-space>
          <div v-if="form.tags.length" class="tag-list">
            <a-tag
              v-for="(tag, idx) in form.tags"
              :key="idx"
              closable
              color="geekblue"
              @close="form.tags.splice(idx, 1)"
              >{{ tag }}</a-tag
            >
          </div>
        </a-form-item>

        <a-form-item label="前置依赖知识点">
          <a-select
            v-model:value="form.prerequisites"
            mode="multiple"
            placeholder="选择前置知识点"
            style="width: 100%"
            :options="availablePrereqs.map((kp) => ({ value: kp.id, label: kp.name }))"
            :filter-option="
              (input: string, option: any) =>
                option.label.toLowerCase().includes(input.toLowerCase())
            "
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script lang="ts">
import { PlusOutlined } from '@ant-design/icons-vue'

export default {
  components: { PlusOutlined }
}
</script>

<style scoped>
.kp-manage-page {
  max-width: 1400px;
  margin: 0 auto;
}

/* ========== 页面标题 ========== */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: #f8fafc;
  margin: 0;
}
.page-subtitle {
  color: #94a3b8;
  font-size: 13px;
  margin: 4px 0 0;
}
.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

/* ========== 筛选栏 ========== */
.filter-bar {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(10px);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

/* ========== 列表 ========== */
.kp-list {
  background: rgba(255, 255, 255, 0.04);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
}
.kp-name {
  font-weight: 600;
  color: #d4a373;
}
.prereq-text {
  font-size: 12px;
  color: #94a3b8;
}
.text-muted {
  color: #94a3b8;
  font-size: 12px;
}

/* ========== 图谱视图 ========== */
.graph-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.graph-layer {
  background: rgba(255, 255, 255, 0.04);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 12px 16px;
}
.layer-header {
  margin-bottom: 10px;
}
.layer-tag {
  font-weight: 600;
  font-size: 13px;
}
.layer-nodes {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}
.graph-node-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 12px;
  transition: box-shadow 0.2s;
}
.graph-node-card:hover {
  box-shadow: 0 2px 8px rgba(74, 108, 247, 0.15);
}
.node-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.node-name {
  font-weight: 600;
  font-size: 14px;
  color: #f8fafc;
}
.node-desc {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.node-prereqs {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 4px;
}
.prereq-label {
  color: #94a3b8;
}
.prereq-list {
  color: #d4a373;
}
.node-actions {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding-top: 8px;
}
.empty-nodes {
  color: #94a3b8;
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

.graph-legend {
  background: rgba(255, 255, 255, 0.04);
  border-radius: 8px;
  padding: 12px 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.legend-title {
  font-size: 13px;
  font-weight: 600;
  color: #94a3b8;
}
.legend-edges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}
.legend-edge {
  font-size: 12px;
  color: #d4a373;
  background: rgba(212, 163, 115, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
}
.legend-more {
  font-size: 12px;
  color: #94a3b8;
}

/* ========== 表单 ========== */
.kp-form {
  margin-top: 8px;
}
.tag-list {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
