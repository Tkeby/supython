<script setup lang="ts">
import { computed } from 'vue'
import { NSpace, NButton, NText, NTag } from 'naive-ui'
import SqlEditor from './SqlEditor.vue'

const props = defineProps<{
  ddl: string
  sampleQuery: string
  running?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:ddl', v: string): void
  (e: 'update:sampleQuery', v: string): void
  (e: 'run'): void
}>()

const ddlBytes = computed(() => new TextEncoder().encode(props.ddl).length)
const nearLimit = computed(() => ddlBytes.value > 7000)
const overLimit = computed(() => ddlBytes.value > 8192)
</script>

<template>
  <NSpace vertical :size="16">
    <div>
      <div
        style="
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        "
      >
        <NText strong>Policy DDL</NText>
        <NTag
          :type="overLimit ? 'error' : nearLimit ? 'warning' : 'default'"
          size="small"
        >
          {{ ddlBytes }} / 8192 bytes
        </NTag>
      </div>
      <SqlEditor
        :model-value="ddl"
        @update:model-value="emit('update:ddl', $event)"
        height="160px"
      />
    </div>

    <div>
      <div style="margin-bottom: 8px">
        <NText strong>Sample Query</NText>
      </div>
      <SqlEditor
        :model-value="sampleQuery"
        @update:model-value="emit('update:sampleQuery', $event)"
        height="120px"
        :on-run="() => emit('run')"
      />
    </div>

    <NSpace justify="end">
      <NButton
        type="primary"
        :loading="running"
        :disabled="overLimit || !ddl.trim() || !sampleQuery.trim()"
        @click="emit('run')"
      >
        Run Dry-Run
      </NButton>
    </NSpace>
  </NSpace>
</template>
