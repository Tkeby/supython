<script setup lang="ts">
import { computed } from 'vue'
import { NDatePicker } from 'naive-ui'
import type { FilterDef, FilterValue } from './types'

const props = defineProps<{
  def: Extract<FilterDef, { type: 'date' }>
}>()

const value = defineModel<FilterValue>({ default: null })

const timestamp = computed({
  get: () => {
    const v = value.value as string | null
    if (!v) return null
    const ts = new Date(v).getTime()
    return isNaN(ts) ? null : ts
  },
  set: (ts: number | null) => {
    if (!ts) {
      value.value = null
    } else {
      const d = new Date(ts)
      value.value = d.toISOString().slice(0, 10) // YYYY-MM-DD
    }
  },
})
</script>

<template>
  <NDatePicker
    v-model:value="timestamp"
    :placeholder="def.placeholder ?? def.label ?? 'Select date…'"
    type="date"
    clearable
    :style="{ width: typeof def.width === 'number' ? `${def.width}px` : (def.width ?? '160px') }"
  />
</template>
