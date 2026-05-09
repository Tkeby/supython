<script setup lang="ts">
import { computed } from 'vue'
import type { FilterDef, FilterValue, FilterValues } from './filters/types'
import { FILTER_COMPONENTS } from './filters/registry'

const props = defineProps<{
  placeholder?: string
  filters?: FilterDef[]
}>()

const search = defineModel<string>('search', { default: '' })
const values = defineModel<FilterValues>('values', { default: () => ({}) })
defineEmits<{ (e: 'refresh'): void }>()

const hasDeclarativeFilters = computed(
  () => Array.isArray(props.filters) && props.filters.length > 0,
)

function getValue(key: string): FilterValue {
  return (values.value?.[key] ?? null) as FilterValue
}
function setValue(key: string, v: FilterValue): void {
  values.value = { ...values.value, [key]: v }
}
</script>

<template>
  <div class="filter-bar">
    <input
      v-model="search"
      :placeholder="placeholder ?? 'Search…'"
      class="filter-bar__search"
    />

    <template v-if="hasDeclarativeFilters">
      <div
        v-for="def in filters"
        :key="def.key"
        class="filter-bar__field"
      >
        <label v-if="def.label" class="filter-bar__label">{{ def.label }}</label>
        <component
          :is="FILTER_COMPONENTS[def.type]"
          :def="def"
          :model-value="getValue(def.key)"
          @update:model-value="(v: FilterValue) => setValue(def.key, v)"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  align-items: flex-end;
}
.filter-bar__search {
  flex: 1 1 220px;
  min-width: 200px;
  padding: 6px 10px;
  border-radius: 4px;
  border: 1px solid var(--n-border-color, rgba(255, 255, 255, 0.12));
  background: rgba(255, 255, 255, 0.05);
  color: inherit;
  font-size: 13px;
  outline: none;
  height: 34px;
  box-sizing: border-box;
}
.filter-bar__field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.filter-bar__label {
  font-size: 11px;
  color: var(--n-text-color-3, rgba(255, 255, 255, 0.55));
}
</style>
