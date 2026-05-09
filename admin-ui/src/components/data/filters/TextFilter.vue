<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { NInput } from 'naive-ui'
import type { FilterDef, FilterValue } from './types'

const props = defineProps<{
  def: Extract<FilterDef, { type: 'text' }>
}>()

const value = defineModel<FilterValue>({ default: null })
const local = ref<string>((value.value as string | null) ?? '')

let timer: ReturnType<typeof setTimeout> | null = null

watch(local, (v) => {
  if (timer) clearTimeout(timer)
  const wait = props.def.debounceMs ?? 0
  const commit = () => {
    value.value = v === '' ? null : v
  }
  if (wait > 0) {
    timer = setTimeout(commit, wait)
  } else {
    commit()
    timer = null
  }
})

watch(
  () => value.value,
  (v) => {
    const next = (v as string | null) ?? ''
    if (next !== local.value) local.value = next
  },
)

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <NInput
    v-model:value="local"
    :placeholder="def.placeholder ?? def.label ?? 'Filter…'"
    clearable
    :style="{ width: typeof def.width === 'number' ? `${def.width}px` : def.width }"
  />
</template>
