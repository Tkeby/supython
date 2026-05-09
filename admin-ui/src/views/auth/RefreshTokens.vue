<script setup lang="ts">
import { computed, h, ref } from 'vue'
import {
  NButton,
  NCard,
  NDataTable,
  NInput,
  NPagination,
  NSpace,
  NTag,
} from 'naive-ui'
import type { DataTableColumn } from 'naive-ui'
import ResourceTable from '@/components/data/ResourceTable.vue'
import { useTable } from '@/composables/useTable'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { authApi } from '@/api/resources'
import type { RefreshToken } from '@/api/types'

const toast = useToast()
const confirm = useConfirm()

const userIdFilter = ref('')

const { q, data, loading, error, refresh } = useTable((q) =>
  authApi.refreshTokens({
    user_id: userIdFilter.value || undefined,
    limit: q.limit,
    offset: q.offset,
  }),
)

const rows = computed(() => data.value?.rows ?? [])
const total = computed(() => data.value?.total ?? 0)

const columns: DataTableColumn<RefreshToken>[] = [
  { title: 'ID', key: 'id', width: 60 },
  { title: 'User ID', key: 'user_id', width: 340 },
  {
    title: 'Token',
    key: 'token',
    ellipsis: { tooltip: true },
    render: (row) => row.token.slice(0, 12) + '…',
  },
  {
    title: 'Issued',
    key: 'created_at',
    width: 170,
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
  {
    title: 'Parent',
    key: 'parent',
    width: 170,
    render: (row) => (row.parent ? row.parent.slice(0, 12) + '…' : '—'),
  },
  {
    title: 'Revoked',
    key: 'revoked',
    width: 90,
    render: (row) =>
      row.revoked
        ? h(NTag, { type: 'error', size: 'small' }, { default: () => 'Yes' })
        : h(NTag, { type: 'success', size: 'small' }, { default: () => 'No' }),
  },
  {
    title: 'Action',
    key: 'action',
    width: 100,
    render: (row) =>
      !row.revoked
        ? h(
            NButton,
            {
              size: 'tiny',
              type: 'error',
              secondary: true,
              onClick: () => handleRevoke(row),
            },
            { default: () => 'Revoke' },
          )
        : null,
  },
]

async function handleRevoke(token: RefreshToken) {
  const ok = await confirm(
    'Revoke refresh token?',
    `Revoke token ${token.id} for user ${token.user_id}? This will log them out if it was their most recent token.`,
  )
  if (!ok) return
  try {
    await authApi.revokeToken(token.id)
    toast.success(`Token ${token.id} revoked.`)
    await refresh()
  } catch (e: unknown) {
    toast.error((e as { message?: string }).message ?? 'Revoke failed')
  }
}
</script>

<template>
  <NCard title="Refresh Tokens" size="small">
    <NSpace vertical :size="16">
      <!-- User ID filter -->
      <NSpace align="end">
        <div>
          <div style="margin-bottom: 4px; font-size: 12px; color: rgba(255,255,255,0.55)">
            Filter by User ID (optional)
          </div>
          <NInput
            v-model:value="userIdFilter"
            placeholder="e.g. 550e8400-e29b-41d4-a716-446655440000"
            clearable
            style="width: 380px"
            @keyup.enter="refresh"
            @clear="refresh()"
          />
        </div>
        <NButton size="small" secondary @click="refresh">Apply</NButton>
      </NSpace>

      <!-- Table -->
      <ResourceTable
        :q="q"
        :rows="rows"
        :total="total"
        :loading="loading"
        :error="error"
        :columns="columns"
        search-placeholder="Filter rows…"
        @refresh="refresh"
      >
        <template #default>
          <NDataTable
            :columns="columns"
            :data="rows"
            :bordered="false"
          />
          <NPagination
            :page="Math.floor(q.offset / q.limit) + 1"
            :page-count="Math.max(1, Math.ceil(total / q.limit))"
            style="margin-top: 12px"
            @update:page="(p: number) => (q.offset = (p - 1) * q.limit)"
          />
        </template>
      </ResourceTable>
    </NSpace>
  </NCard>
</template>
