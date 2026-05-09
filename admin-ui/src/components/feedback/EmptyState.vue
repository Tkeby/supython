<script setup lang="ts">
import { NEmpty } from 'naive-ui'

const props = defineProps<{
  description: string
}>()
</script>

<template>
  <NEmpty :description="props.description" />
</template>
