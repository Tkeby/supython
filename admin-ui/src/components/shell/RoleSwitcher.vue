<script setup lang="ts">
import { NSelect, NInput, NSpace, NTag } from 'naive-ui'
import { useUiStore } from '@/stores/ui'
const ui = useUiStore()

const options = [
  { label: 'service_role (bypasses RLS)', value: 'service_role' },
  { label: 'authenticated', value: 'authenticated' },
  { label: 'anon', value: 'anon' },
]
</script>

<template>
  <NSpace align="center">
    <NTag :type="ui.rolePreview.role === 'service_role' ? 'warning' : 'info'">
      Preview as
    </NTag>
    <NSelect
      :value="ui.rolePreview.role" :options="options" style="width: 240px"
      @update:value="(v) => ui.setRolePreview({ role: v })"
    />
    <NInput
      v-if="ui.rolePreview.role === 'authenticated'"
      :value="ui.rolePreview.sub ?? ''" placeholder="impersonate_sub (uuid)"
      @update:value="(v) => ui.setRolePreview({ role: 'authenticated', sub: v })"
    />
  </NSpace>
</template>