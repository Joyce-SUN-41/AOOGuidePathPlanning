<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message, Modal } from 'ant-design-vue'
import type { QuestionItem, QuestionForm, KnowledgePoint } from '@/types'
import { questionApi, knowledgeApi } from '@/api/modules/knowledge'
import { useIsMobile } from '@/composables/useIsMobile'

// 移动端断点
const { isMobile } = useIsMobile()

// ========== 数据状态 ==========
const loading = ref(false)
const questions = ref<QuestionItem[]>([])
const knowledgePoints = ref<KnowledgePoint[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

// 筛选
const filterSubject = ref('')
const filterDifficulty = ref<number | undefined>(undefined)
const filterKpId = ref('')

// ========== 编辑对话框 ==========
const modalVisible = ref(false)
const modalTitle = ref('新增题目')
const isEditing = ref(false)
const editingId = ref('')
const form = reactive<QuestionForm>({
  code: '',
  kp_ids: [],
  subject: '人工智能导论',
  difficulty: 1,
  type: 'single',
  title: '',
  options: [
    { id: 'A', text: '', weight: 1.0 },
    { id: 'B', text: '', weight: 0.0 },
    { id: 'C', text: '', weight: 0.0 },
    { id: 'D', text: '', weight: 0.0 }
  ],
  correct_option_id: 'A',
  expected_time_sec: 30,
  explanation: ''
})

// ========== 选项常量 ==========
const difficultyLevels = [1, 2, 3, 4, 5]

// ========== 方法 ==========
async function loadQuestions() {
  loading.value = true
  try {
    const result = await questionApi.list({
      subject: filterSubject.value || undefined,
      difficulty: filterDifficulty.value,
      kp_id: filterKpId.value || undefined,
      page: currentPage.value,
      page_size: pageSize.value
    })
    questions.value = result.items
    total.value = result.total
  } catch (e) {
    message.error('加载题库失败')
  } finally {
    loading.value = false
  }
}

async function loadKnowledgePoints() {
  try {
    knowledgePoints.value = await knowledgeApi.list()
  } catch {
    // ignore
  }
}

function onPageChange(page: number) {
  currentPage.value = page
  loadQuestions()
}

// 难度颜色
function getDifficultyColor(level: number): string {
  const colors: Record<number, string> = { 1: 'green', 2: 'cyan', 3: 'blue', 4: 'orange', 5: 'red' }
  return colors[level] || 'default'
}

// 打开新增
function openCreate() {
  isEditing.value = false
  editingId.value = ''
  modalTitle.value = '新增题目'
  Object.assign(form, {
    code: `q_ai_${String(questions.value.length + 1).padStart(3, '0')}`,
    kp_ids: [],
    subject: '人工智能导论',
    difficulty: 1,
    type: 'single',
    title: '',
    options: [
      { id: 'A', text: '', weight: 1.0 },
      { id: 'B', text: '', weight: 0.0 },
      { id: 'C', text: '', weight: 0.0 },
      { id: 'D', text: '', weight: 0.0 }
    ],
    correct_option_id: 'A',
    expected_time_sec: 30,
    explanation: ''
  })
  modalVisible.value = true
}

// 打开编辑
function openEdit(q: QuestionItem) {
  isEditing.value = true
  editingId.value = q.id
  modalTitle.value = `编辑题目: ${q.code}`
  Object.assign(form, {
    code: q.code,
    kp_ids: [...q.kp_ids],
    subject: q.subject,
    difficulty: q.difficulty,
    type: q.type,
    title: q.title,
    options: q.options.map((o) => ({ ...o })),
    correct_option_id: q.correct_option_id,
    expected_time_sec: q.expected_time_sec,
    explanation: q.explanation || ''
  })
  modalVisible.value = true
}

// 提交
async function handleSubmit() {
  if (!form.title.trim()) {
    message.warning('请输入题目标题')
    return
  }
  if (!form.kp_ids.length) {
    message.warning('请选择关联知识点')
    return
  }
  if (form.options.some((o) => !o.text.trim())) {
    message.warning('请填写所有选项文本')
    return
  }

  try {
    if (isEditing.value) {
      await questionApi.update(editingId.value, form)
      message.success('题目更新成功')
    } else {
      await questionApi.create(form)
      message.success('题目创建成功')
    }
    modalVisible.value = false
    await loadQuestions()
  } catch (e: unknown) {
    const errMsg = e instanceof Error ? e.message : '操作失败'
    message.error(errMsg)
  }
}

// 删除
function handleDelete(q: QuestionItem) {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除题目 "${q.code} - ${q.title.substring(0, 30)}..." 吗？`,
    okText: '确定删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await questionApi.delete(q.id)
        message.success('题目已删除')
        await loadQuestions()
      } catch (e: unknown) {
        const errMsg = e instanceof Error ? e.message : '删除失败'
        message.error(errMsg)
      }
    }
  })
}

// ========== 生命周期 ==========
onMounted(() => {
  loadQuestions()
  loadKnowledgePoints()
})
</script>

<template>
  <div class="qb-manage-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <div>
        <h1 class="page-title">题库管理</h1>
        <p class="page-subtitle">管理诊断测验的题目资源，支持创建、编辑、删除和批量导入</p>
      </div>
      <a-button type="primary" @click="openCreate">
        <template #icon><PlusOutlined /></template>
        新增题目
      </a-button>
    </div>

    <!-- ========== 筛选栏 ========== -->
    <div class="filter-bar">
      <a-space>
        <a-select
          v-model:value="filterSubject"
          placeholder="学科筛选"
          style="width: 160px"
          allow-clear
          @change="loadQuestions"
          :options="['人工智能导论'].map((s) => ({ value: s, label: s }))"
        />
        <a-select
          v-model:value="filterDifficulty"
          placeholder="难度筛选"
          style="width: 120px"
          allow-clear
          @change="loadQuestions"
          :options="difficultyLevels.map((d) => ({ value: d, label: `Lv${d}` }))"
        />
        <a-select
          v-model:value="filterKpId"
          placeholder="知识点筛选"
          style="width: 200px"
          allow-clear
          show-search
          @change="loadQuestions"
          :options="knowledgePoints.map((kp) => ({ value: kp.id, label: kp.name }))"
          :filter-option="
            (input: string, option: any) => option.label.toLowerCase().includes(input.toLowerCase())
          "
        />
        <a-tag color="blue">共 {{ total }} 道题目</a-tag>
      </a-space>
    </div>

    <a-spin :spinning="loading">
      <!-- ========== 题目列表 ========== -->
      <div class="qb-list">
        <a-table
          :data-source="questions"
          :scroll="{ x: 'max-content' }"
          :pagination="{
            current: currentPage,
            pageSize,
            total,
            showSizeChanger: false,
            onChange: onPageChange
          }"
          row-key="id"
          size="middle"
        >
          <a-table-column title="编号" data-index="code" :width="100">
            <template #default="{ record }">
              <a-tag color="blue" size="small">{{ record.code }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="题目" data-index="title" :width="320" ellipsis>
            <template #default="{ record }">
              <span class="qb-title">{{ record.title }}</span>
            </template>
          </a-table-column>
          <a-table-column title="关联知识点" :width="200">
            <template #default="{ record }">
              <a-space v-if="record.kp_names?.length" :size="4" wrap>
                <a-tag v-for="name in record.kp_names" :key="name" color="geekblue" size="small">{{
                  name
                }}</a-tag>
              </a-space>
              <span v-else class="text-muted">—</span>
            </template>
          </a-table-column>
          <a-table-column title="难度" data-index="difficulty" :width="80" align="center">
            <template #default="{ record }">
              <a-tag :color="getDifficultyColor(record.difficulty)"
                >Lv{{ record.difficulty }}</a-tag
              >
            </template>
          </a-table-column>
          <a-table-column title="题型" data-index="type" :width="80" align="center">
            <template #default="{ record }">
              <span>{{ record.type === 'single' ? '单选' : '多选' }}</span>
            </template>
          </a-table-column>
          <a-table-column
            title="正确答案"
            data-index="correct_option_id"
            :width="80"
            align="center"
          >
            <template #default="{ record }">
              <a-tag color="success">{{ record.correct_option_id }}</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="预计用时" :width="90" align="center">
            <template #default="{ record }">
              <span class="text-secondary">{{ record.expected_time_sec }}s</span>
            </template>
          </a-table-column>
          <a-table-column title="状态" :width="80" align="center">
            <template #default="{ record }">
              <a-tag v-if="record.is_active" color="green">启用</a-tag>
              <a-tag v-else color="red">禁用</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="操作" :width="140" align="center" fixed="right">
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
    </a-spin>

    <!-- ========== 新增/编辑对话框 ========== -->
    <a-modal
      v-model:open="modalVisible"
      :title="modalTitle"
      :width="isMobile ? '90%' : 720"
      @ok="handleSubmit"
      ok-text="保存"
      cancel-text="取消"
      :destroy-on-close="true"
    >
      <a-form layout="vertical" class="qb-form">
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="题目编号" required>
              <a-input v-model:value="form.code" placeholder="如 q_ai_001" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="难度等级" required>
              <a-select
                v-model:value="form.difficulty"
                :options="difficultyLevels.map((d) => ({ value: d, label: `Lv${d}` }))"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="预计用时(秒)">
              <a-input-number
                v-model:value="form.expected_time_sec"
                :min="5"
                :max="600"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="学科">
              <a-input v-model:value="form.subject" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="题型">
              <a-select
                v-model:value="form.type"
                :options="[
                  { value: 'single', label: '单选题' },
                  { value: 'multiple', label: '多选题' }
                ]"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="关联知识点" required>
          <a-select
            v-model:value="form.kp_ids"
            mode="multiple"
            placeholder="选择关联的知识点"
            style="width: 100%"
            :options="knowledgePoints.map((kp) => ({ value: kp.id, label: kp.name }))"
            :filter-option="
              (input: string, option: any) =>
                option.label.toLowerCase().includes(input.toLowerCase())
            "
          />
        </a-form-item>

        <a-form-item label="题目标题" required>
          <a-textarea v-model:value="form.title" :rows="2" placeholder="输入题目内容..." />
        </a-form-item>

        <a-form-item label="选项列表" required>
          <div class="options-editor">
            <div v-for="opt in form.options" :key="opt.id" class="option-row">
              <a-tag
                :color="opt.id === form.correct_option_id ? 'success' : 'default'"
                class="option-id"
              >
                {{ opt.id }}
              </a-tag>
              <a-input
                v-model:value="opt.text"
                :placeholder="`选项 ${opt.id} 内容`"
                style="flex: 1"
              />
              <a-radio
                :checked="opt.id === form.correct_option_id"
                @change="form.correct_option_id = opt.id"
                >正确答案</a-radio
              >
            </div>
          </div>
        </a-form-item>

        <a-form-item label="答案解析">
          <a-textarea v-model:value="form.explanation" :rows="2" placeholder="题目解析 (可选)..." />
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
.qb-manage-page {
  max-width: 1400px;
  margin: 0 auto;
}

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

.filter-bar {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(10px);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.qb-list {
  background: rgba(255, 255, 255, 0.04);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
}
.qb-title {
  font-weight: 500;
}
.text-muted {
  color: #94a3b8;
  font-size: 12px;
}
.text-secondary {
  color: #94a3b8;
  font-size: 12px;
}

/* ========== 选项编辑器 ========== */
.options-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.option-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.option-id {
  min-width: 32px;
  text-align: center;
  font-weight: 600;
}

.qb-form {
  margin-top: 8px;
}
</style>
