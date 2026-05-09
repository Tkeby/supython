<script setup lang="ts" generic="Row extends Record<string, unknown>">
import { computed } from 'vue'
import { NDrawer, NDrawerContent, NDescriptions, NDescriptionsItem, NText } from 'naive-ui'
import JsonField from './JsonField.vue'

const props = defineProps<{
  show: boolean
  row: Row | null
  title?: string
}>()

const emit = defineEmits<{
  (e: 'update:show', val: boolean): void
}>()

const entries = computed(() => {
  if (!props.row) return []
  return Object.entries(props.row)
})
</script>

<template>
  <NDrawer
    :show="show"
    :width="480"
    placement="right"
    :mask-closable="true"
    @update:show="emit('update:show', $event)"
  >
    <NDrawerContent :title="title ?? 'Record detail'" closable>
      <NDescriptions
        v-if="row"
        bordered
        label-placement="top"
        :column="1"
        size="small"
      >
        <NDescriptionsItem
          v-for="[key, val] in entries"
          :key="key"
          :label="key"
        >
          <JsonField :value="val" />
        </NDescriptionsItem>
      </NDescriptions>
      <template v-if="!row">
        <NText depth="3">No row selected.</NText>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
