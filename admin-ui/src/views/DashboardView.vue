<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  NAlert,
  NButton,
  NCard,
  NGrid,
  NGridItem,
  NList,
  NListItem,
  NSpace,
  NSpin,
  NTag,
  NText,
  NThing,
} from 'naive-ui'
import { useResource } from '@/composables/useResource'
import { systemApi, authApi } from '@/api/resources'

const router = useRouter()

const {
  data: status,
  error: statusError,
  loading: statusLoading,
  refresh: refreshStatus,
} = useResource(() => systemApi.status())

const {
  data: auditData,
  error: auditError,
  loading: auditLoading,
} = useResource(() => authApi.audit({ limit: 5 }))

const auditRows = computed(() => auditData.value?.rows ?? [])

function statusType(val: boolean | undefined): 'success' | 'default' | 'warning' | 'error' {
  if (val === undefined) return 'default'
  return val ? 'success' : 'error'
}

function statusText(val: boolean | undefined, on: string, off: string): string {
  if (val === undefined) return off
  return val ? on : off
}

function poolColor(poolSize: number | undefined): 'success' | 'warning' | 'error' {
  if (!poolSize) return 'success'
  // Rough heuristic: if pool_size reads as a single number, treat > 16 as high
  // (backend may return in-use / max in future; for now use simple threshold)
  return poolSize >= 16 ? 'error' : 'success'
}
</script>

<template>
  <div>
    <h1 style="margin: 0 0 16px 0; font-size: 20px; font-weight: 600">Dashboard</h1>

    <NAlert v-if="statusError" type="error" :title="statusError.message" style="margin-bottom: 16px">
      <NSpace>
        <NText>Unable to load system status.</NText>
        <NButton size="small" @click="refreshStatus">Retry</NButton>
      </NSpace>
    </NAlert>

    <NSpin :show="statusLoading">
      <NGrid cols="1 s:2 m:3" responsive="screen" :x-gap="16" :y-gap="16">
        <!-- Pool size -->
        <NGridItem>
          <NCard
            size="small"
            :segmented="{ content: true }"
            hoverable
            @click="router.push('/db/sql')"
          >
            <template #header>
              <NSpace align="center">
                <NTag :type="poolColor(status?.pool_size)" size="small">Pool</NTag>
                <NText strong>DB Pool</NText>
              </NSpace>
            </template>
            <NSpace vertical>
              <NText style="font-size: 24px; font-weight: 700">
                {{ status?.pool_size ?? '-' }}
              </NText>
              <NText depth="3" style="font-size: 12px">active connections</NText>
            </NSpace>
          </NCard>
        </NGridItem>

        <!-- JWKS kid -->
        <NGridItem>
          <NCard size="small" :segmented="{ content: true }" hoverable>
            <template #header>
              <NSpace align="center">
                <NTag type="default" size="small">JWKS</NTag>
                <NText strong>Active Key</NText>
              </NSpace>
            </template>
            <NSpace vertical>
              <NText code style="font-size: 14px">
                {{ status?.jwks_kid ?? '-' }}
              </NText>
              <NText depth="3" style="font-size: 12px">current kid</NText>
            </NSpace>
          </NCard>
        </NGridItem>

        <!-- Realtime broker -->
        <NGridItem>
          <NCard
            size="small"
            :segmented="{ content: true }"
            hoverable
            @click="router.push('/realtime')"
          >
            <template #header>
              <NSpace align="center">
                <NTag :type="statusType(status?.broker)" size="small">
                  {{ statusText(status?.broker, 'ON', 'OFF') }}
                </NTag>
                <NText strong>Realtime</NText>
              </NSpace>
            </template>
            <NSpace vertical>
              <NText style="font-size: 24px; font-weight: 700">
                {{ statusText(status?.broker, 'Connected', 'Disconnected') }}
              </NText>
              <NText depth="3" style="font-size: 12px">broker status</NText>
            </NSpace>
          </NCard>
        </NGridItem>

        <!-- Jobs worker -->
        <NGridItem>
          <NCard
            size="small"
            :segmented="{ content: true }"
            hoverable
            @click="router.push('/jobs')"
          >
            <template #header>
              <NSpace align="center">
                <NTag :type="statusType(status?.jobs)" size="small">
                  {{ statusText(status?.jobs, 'ON', 'OFF') }}
                </NTag>
                <NText strong>Jobs</NText>
              </NSpace>
            </template>
            <NSpace vertical>
              <NText style="font-size: 24px; font-weight: 700">
                {{ statusText(status?.jobs, 'Enabled', 'Disabled') }}
              </NText>
              <NText depth="3" style="font-size: 12px">worker heartbeat</NText>
            </NSpace>
          </NCard>
        </NGridItem>
      </NGrid>
    </NSpin>

    <!-- Recent audit -->
    <NCard
      title="Recent Audit Events"
      size="small"
      style="margin-top: 24px"
      :segmented="{ content: true }"
    >
      <NSpin :show="auditLoading">
        <NAlert v-if="auditError" type="error" :title="auditError.message" />
        <NList v-else-if="auditRows.length" hoverable clickable>
          <NListItem
            v-for="row in auditRows"
            :key="(row as any).id ?? JSON.stringify(row)"
            @click="router.push('/auth/audit')"
          >
            <NThing
              :title="(row as any).event ?? (row as any).action ?? 'Unknown'"
              :description="(row as any).target ?? ''"
            >
              <template #header-extra>
                <NText depth="3" style="font-size: 12px">
                  {{ (row as any).at ? new Date((row as any).at).toLocaleString() : '' }}
                </NText>
              </template>
            </NThing>
          </NListItem>
        </NList>
        <NSpace v-else vertical align="center" style="padding: 32px">
          <NText depth="3">No recent audit events.</NText>
        </NSpace>
      </NSpin>
    </NCard>
  </div>
</template>
