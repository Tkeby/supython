<script setup lang="ts">
import { computed } from 'vue'
import { NSelect } from 'naive-ui'
import type { FilterDef, FilterValue } from './types'

const props = defineProps<{
  def: Extract<FilterDef, { type: 'select' }>
}>()

const value = defineModel<FilterValue>({ default: null })

const options = computed(() =>
  props.def.options.map((o) => ({ label: o.label, value: o.value as never })),
)
</script>

<template>
  <NSelect
    :value="value as never"
    :options="options"
    :placeholder="def.placeholder ?? def.label ?? 'Select…'"
    :clearable="def.clearable ?? true"
    :style="{ minWidth: typeof def.width === 'number' ? `${def.width}px` : (def.width ?? '160px') }"
    @update:value="(v: FilterValue) => (value = v)"
  />
</template>
