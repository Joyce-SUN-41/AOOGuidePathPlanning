<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  CheckOutlined,
  SendOutlined,
  ReloadOutlined,
  BulbOutlined,
} from '@ant-design/icons-vue'

const props = defineProps<{
  reflecting?: boolean
  understood?: boolean
  feedback?: string
  followUp?: string
}>()

const emit = defineEmits<{
  (e: 'acknowledge', checked: boolean): void
  (e: 'submit-reflect', question: string): void
  (e: 'request-regenerate', newIdea: string): void
}>()

const acknowledged = ref(false)
const question = ref('')
const showRegenerate = ref(false)
const newIdea = ref('')

const canSubmit = computed(
  () => acknowledged.value && question.value.trim().length > 0 && !props.reflecting,
)

const feedbackAlertType = computed(() => (props.understood ? 'success' : 'warning'))

function onAcknowledge(e: any) {
  acknowledged.value = e.target.checked
  emit('acknowledge', acknowledged.value)
}

function submitReflect() {
  if (!canSubmit.value) return
  emit('submit-reflect', question.value.trim())
}

function submitRegenerate() {
  const idea = newIdea.value.trim()
  if (!idea) return
  emit('request-regenerate', idea)
  showRegenerate.value = false
  newIdea.value = ''
}
</script>

<template>
  <div class="reflect-gate">
    <div class="reflect-head">
      <BulbOutlined class="reflect-bulb" />
      <span class="reflect-title">这段素材可直接使用，先确认你读懂了</span>
    </div>

    <div class="reflect-body">
      <label class="reflect-check">
        <a-checkbox :checked="acknowledged" @change="onAcknowledge">
          我已读懂这段内容
        </a-checkbox>
      </label>

      <a-textarea
        v-model:value="question"
        class="reflect-input"
        placeholder="用自己的话，向老师提一个关于这段素材的问题"
        :auto-size="{ minRows: 2, maxRows: 4 }"
        :disabled="reflecting"
      />

      <a-button
        type="primary"
        class="reflect-submit"
        :disabled="!canSubmit"
        :loading="reflecting"
        @click="submitReflect"
      >
        <template v-if="!reflecting"><SendOutlined /> 提交反思</template>
        <template v-else>判定中</template>
      </a-button>
    </div>

    <a-alert
      v-if="feedback"
      class="reflect-feedback"
      :type="feedbackAlertType"
      :show-icon="true"
      :message="understood ? '理解到位' : '还需再想想'"
      :description="feedback + (followUp ? '　' + followUp : '')"
    />

    <div v-if="understood" class="reflect-regenerate">
      <a-button
        v-if="!showRegenerate"
        class="reflect-regen-btn"
        @click="showRegenerate = true"
      >
        <ReloadOutlined /> 用我的新思路重生成
      </a-button>
      <div v-else class="reflect-regen-box">
        <a-textarea
          v-model:value="newIdea"
          class="reflect-input"
          placeholder="说说你的新思路，AI 将据此重新生成这段素材"
          :auto-size="{ minRows: 2, maxRows: 4 }"
        />
        <a-button type="primary" class="reflect-regen-confirm" @click="submitRegenerate">
          <CheckOutlined /> 据此重生成
        </a-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.reflect-gate {
  margin: 8px 0 4px;
  padding: 12px 14px;
  border: 1px solid rgba(212, 163, 115, 0.35);
  border-radius: 2px;
  background: rgba(212, 163, 115, 0.06);
}
.reflect-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.reflect-bulb {
  color: #d4a373;
}
.reflect-title {
  font-size: 13px;
  color: #cbd5e1;
  font-weight: 600;
}
.reflect-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.reflect-check :deep(.ant-checkbox-wrapper) {
  color: #e2e8f0;
}
.reflect-input {
  background: rgba(6, 8, 13, 0.6);
}
.reflect-submit {
  align-self: flex-start;
}
.reflect-feedback {
  margin-top: 10px;
  background: rgba(6, 8, 13, 0.5);
  border-radius: 2px;
}
.reflect-regenerate {
  margin-top: 10px;
}
.reflect-regen-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.reflect-regen-confirm {
  align-self: flex-start;
}
</style>
