<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  NCard,
  NSpace,
  NSwitch,
  NButton,
  NSelect,
  NDataTable,
  NTag,
  NText,
  NSpin,
} from 'naive-ui'
import SqlEditor from '@/components/editors/SqlEditor.vue'
import EmptyState from '@/components/feedback/EmptyState.vue'
import ErrorState from '@/components/feedback/ErrorState.vue'
import { useConfirm } from '@/composables/useConfirm'
import { useToast } from '@/composables/useToast'
import { dbApi } from '@/api/resources'
import type { SqlResult } from '@/api/types'

const confirm = useConfirm()
const toast = useToast()

const statement = ref('')
const readOnly = ref(true)
const running = ref(false)
const result = ref<SqlResult | null>(null)
const execError = ref<string | null>(null)

interface HistoryItem {
  label: string
  value: string
  at: number
}

const history = ref<HistoryItem[]>([])
const selectedHistory = ref<string | null>(null)

const historyOptions = computed(() =>
  history.value.map((h, idx) => ({
    label: `${h.label} \u2014 ${new Date(h.at).toLocaleTimeString()}`,
    value: String(idx),
  })),
)

function addToHistory(sql: string) {
  const trimmed = sql.trim()
  if (!trimmed) return
  if (history.value[0]?.value === trimmed) return
  const label = trimmed.split('\n')[0].slice(0, 60) || trimmed.slice(0, 60)
  history.value.unshift({ label, value: trimmed, at: Date.now() })
  if (history.value.length > 20) history.value.pop()
}

function onSelectHistory(idxStr: string) {
  const idx = parseInt(idxStr, 10)
  const item = history.value[idx]
  if (item) statement.value = item.value
}

async function toggleReadOnly(next: boolean) {
  if (!next) {
    const ok = await confirm(
      'Enable write mode?',
      'You are about to allow INSERT, UPDATE, DELETE and DDL. Changes commit immediately. Continue?',
    )
    if (!ok) {
      readOnly.value = true
      return
    }
  }
  readOnly.value = next
}

async function run() {
  const sql = statement.value.trim()
  if (!sql) {
    toast.warning('Enter a SQL statement')
    return
  }
  running.value = true
  result.value = null
  execError.value = null
  try {
    const res = await dbApi.runSql(sql, readOnly.value)
    result.value = res
    addToHistory(sql)
    toast.success(`${res.row_count} row${res.row_count === 1 ? '' : 's'}`)
  } catch (e: any) {
    execError.value = e.message ?? 'Query failed'
    toast.error(execError.value as any)
  } finally {
    running.value = false
  }
}

const resultColumns = computed(() =>
  result.value ? result.value.columns.map((c) => ({ title: c, key: c })) : [],
)

const resultRows = computed(() => {
  if (!result.value) return []
  return result.value.rows.map((row) =>
    Object.fromEntries(
      result.value!.columns.map((col, i) => {
        const val = row[i]
        let text: string
        if (val === null) text = 'null'
        else if (typeof val === 'object') text = JSON.stringify(val)
        else text = String(val)
        return [col, text]
      }),
    ),
  )
})
</script>

<template>
  <NCard title="SQL Workspace">
    <NSpace vertical :size="16">
      <!-- Toolbar -->
      <NSpace align="center" justify="space-between">
        <NSpace align="center" :size="12">
          <NSelect
            v-model:value="selectedHistory"
            :options="historyOptions"
            placeholder="History"
            clearable
            style="width: 260px"
            @update:value="onSelectHistory"
          />
          <NButton type="primary" :loading="running" @click="run">
            Run
          </NButton>
          <NTag v-if="readOnly" type="default" size="small">Read-only</NTag>
          <NTag v-else type="warning" size="small">Write enabled</NTag>
        </NSpace>

        <NSpace align="center" :size="8">
          <NText depth="3" style="font-size: 12px">Read-only</NText>
          <NSwitch
            :value="readOnly"
            :round="false"
            @update:value="toggleReadOnly"
          >
            <template #checked-icon>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                <rect x="3" y="11" width="18" height="11" rx="2" />
                <path d="M7 11V7a5 5 0 0110 0v4" />
              </svg>
            </template>
            <template #unchecked-icon>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </template>
          </NSwitch>
        </NSpace>
      </NSpace>

      <!-- Editor -->
      <SqlEditor
        v-model="statement"
        :height="'280px'"
        :on-run="run"
        :style="readOnly ? {} : { border: '1px solid var(--n-warning-color)' }"
      />

      <!-- Results -->
      <NSpin :show="running">
        <ErrorState v-if="execError" :error="{ message: execError }" :retry="run" />
        <div v-else-if="result">
          <NSpace align="center" :size="8" style="margin-bottom: 8px">
            <NText depth="3" style="font-size: 12px">
              {{ result.row_count }} row{{ result.row_count === 1 ? '' : 's' }}
            </NText>
          </NSpace>
          <NDataTable
            v-if="resultRows.length"
            :columns="resultColumns"
            :data="resultRows"
            :bordered="false"
            size="small"
            :scroll-x="600"
          />
          <EmptyState
            v-else
            description="Query executed successfully. No rows returned."
          />
        </div>
        <EmptyState
          v-else
          description="Write a SQL query and press Run (Ctrl+Enter) to see results."
        />
      </NSpin>
    </NSpace>
  </NCard>
</template>
