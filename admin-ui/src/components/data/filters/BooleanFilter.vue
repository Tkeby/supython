<script setup lang="ts">
import { computed } from 'vue'
import { NSelect } from 'naive-ui'
import type { FilterDef, FilterValue } from './types'

const props = defineProps<{
  def: Extract<FilterDef, { type: 'boolean' }>
}>()

const value = defineModel<FilterValue>({ default: null })

const options = computed(() => [
  { label: props.def.anyLabel ?? 'Any', value: null as never },
  { label: props.def.trueLabel ?? 'Yes', value: true as never },
  { label: props.def.falseLabel ?? 'No', value: false as never },
])
</script>

<template>
  <NSelect
    :value="value as never"
    :options="options"
    :placeholder="def.label ?? 'Any'"
    :clearable="false"
    :style="{ minWidth: typeof def.width === 'number' ? `${def.width}px` : (def.width ?? '120px') }"
    @update:value="(v: FilterValue) => (value = v)"
  />
</template>
