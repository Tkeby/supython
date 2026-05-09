<script setup lang="ts">
import { NAlert, NSpace, NButton } from 'naive-ui'

const props = defineProps<{
  error: { message: string } | null
  retry?: () => void
}>()
</script>

<template>
  <NAlert v-if="error" type="error" :title="error.message">
    <NSpace>
      <NButton v-if="retry" size="small" @click="retry">Retry</NButton>
    </NSpace>
  </NAlert>
</template>
