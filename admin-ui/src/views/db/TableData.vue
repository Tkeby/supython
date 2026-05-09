<script setup lang="ts">
import { computed, h, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NCard, NSpace, NAlert } from 'naive-ui'
import ResourceTable from '@/components/data/ResourceTable.vue'
import JsonField from '@/components/data/JsonField.vue'
import RoleSwitcher from '@/components/shell/RoleSwitcher.vue'
import { useTable } from '@/composables/useTable'
import { useImpersonate } from '@/composables/useImpersonate'
import { dbApi } from '@/api/resources'

const route = useRoute()
const { rolePreview, params: previewParams } = useImpersonate()

const schema = computed(() => route.params.schema as string)
const table = computed(() => route.params.table as string)

const isPreview = computed(() => rolePreview.role !== 'service_role')
const needsSub = computed(() => rolePreview.role === 'authenticated' && !rolePreview.sub)

const { q, data, loading, error, refresh } = useTable(async (q) => {
  if (needsSub.value) {
    return { rows: [], total: 0 }
  }
  const page = await dbApi.rows(schema.value, table.value, {
    limit: q.limit,
    offset: q.offset,
    order: q.order ?? '',
    role: previewParams.value.role,
    impersonate_sub: previewParams.value.impersonate_sub,
  })
  const rows = page.rows.map((r) =>
    Object.fromEntries(page.columns.map((c, i) => [c, r[i]])),
  )
  return { rows, total: page.total }
})

watch(
  () => ({ role: rolePreview.role, sub: rolePreview.sub }),
  refresh,
  { deep: true },
)

const rows = computed(() => data.value?.rows ?? [])
const total = computed(() => data.value?.total ?? 0)

const columns = computed(() =>
  (rows.value[0] ? Object.keys(rows.value[0]) : []).map((c) => ({
    title: c,
    key: c,
    render: (row: Record<string, unknown>) => h(JsonField, { value: row[c] }),
  })),
)
</script>

<template>
  <NCard
    :title="`${schema}.${table}`"
    :style="isPreview ? { borderTop: '4px solid var(--n-warning-color)' } : undefined"
  >
    <NSpace vertical :size="16">
      <RoleSwitcher />
      <NAlert
        v-if="needsSub"
        type="warning"
        title="Provide an impersonation UUID to preview as a specific user."
      />
      <ResourceTable
        :q="q"
        :rows="rows"
        :total="total"
        :loading="loading"
        :error="error"
        :columns="columns"
        search-placeholder="Filter…"
        @refresh="refresh"
      />
    </NSpace>
  </NCard>
</template>