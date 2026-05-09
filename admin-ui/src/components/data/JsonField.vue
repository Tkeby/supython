<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NText, NTooltip } from 'naive-ui'

const props = defineProps<{ value: unknown }>()

const expanded = ref(false)

const display = computed(() => {
  if (props.value === null || props.value === undefined) return ''
  return typeof props.value === 'string' ? props.value : JSON.stringify(props.value, null, 2)
})

const collapsed = computed(() => {
  if (props.value === null || props.value === undefined) return ''
  const s = typeof props.value === 'string' ? props.value : JSON.stringify(props.value)
  return s.length > 80 ? s.slice(0, 77) + '…' : s
})

const isObject = computed(() => props.value !== null && typeof props.value === 'object')
</script>

<template>
  <span v-if="value === null || value === undefined">
    <NText depth="3" style="font-style: italic">null</NText>
  </span>
  <template v-else-if="!isObject">
    {{ display }}
  </template>
  <template v-else>
    <NButton
      text
      size="tiny"
      type="info"
      @click="expanded = !expanded"
    >
      {{ expanded ? '▾' : '▸' }}
    </NButton>
    <template v-if="expanded">
      <pre style="margin: 4px 0 0; font-size: 12px; white-space: pre-wrap">{{ display }}</pre>
    </template>
    <template v-else>
      <NTooltip>
        <template #trigger>
          <NText code style="font-size: 12px">{{ collapsed }}</NText>
        </template>
        {{ display }}
      </NTooltip>
    </template>
  </template>
</template>
