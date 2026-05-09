<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NCard,
  NLayout,
  NLayoutSider,
  NLayoutContent,
  NList,
  NListItem,
  NThing,
  NTag,
  NSpin,
  NSpace,
  NEmpty,
} from 'naive-ui'
import EmptyState from '@/components/feedback/EmptyState.vue'
import ErrorState from '@/components/feedback/ErrorState.vue'
import { useResource } from '@/composables/useResource'
import { dbApi } from '@/api/resources'

const router = useRouter()
const selectedSchema = ref<string | null>(null)

const {
  data: schemas,
  error: schemasError,
  loading: schemasLoading,
  refresh: refreshSchemas,
} = useResource(() => dbApi.schemas())

const {
  data: tables,
  error: tablesError,
  loading: tablesLoading,
  refresh: refreshTables,
} = useResource(
  () => (selectedSchema.value ? dbApi.tables(selectedSchema.value) : Promise.resolve([])),
  () => [selectedSchema.value],
)

function selectSchema(name: string) {
  selectedSchema.value = name
}

function goToTable(schema: string, table: string) {
  router.push(`/db/tables/${schema}/${table}`)
}
</script>

<template>
  <NLayout has-sider style="height: calc(100vh - 112px)">
    <NLayoutSider bordered width="260" :native-scrollbar="false">
      <NCard title="Schemas" :bordered="false" size="small">
        <NSpin :show="schemasLoading">
          <ErrorState :error="schemasError" :retry="refreshSchemas" />
          <NList v-if="schemas && schemas.length > 0" hoverable clickable>
            <NListItem
              v-for="s in schemas"
              :key="s.name"
              :class="{ 'schema-active': selectedSchema === s.name }"
              @click="selectSchema(s.name)"
            >
              <NThing :title="s.name" :description="s.owner">
                <template #header-extra>
                  <NTag v-if="!s.is_user" size="small" type="info">system</NTag>
                </template>
              </NThing>
            </NListItem>
          </NList>
          <EmptyState
            v-else-if="schemas && schemas.length === 0"
            description="No schemas found."
          />
        </NSpin>
      </NCard>
    </NLayoutSider>

    <NLayoutContent style="padding: 16px 24px" :native-scrollbar="false">
      <NCard
        :title="selectedSchema ? `Tables in ${selectedSchema}` : 'Tables'"
        :bordered="false"
      >
        <NSpin :show="tablesLoading">
          <ErrorState :error="tablesError" :retry="refreshTables" />
          <template v-if="selectedSchema">
            <NList v-if="tables && tables.length > 0" hoverable clickable>
              <NListItem
                v-for="t in tables"
                :key="t.name"
                @click="goToTable(selectedSchema, t.name)"
              >
                <NThing :title="t.name">
                  <template #header-extra>
                    <NSpace align="center" :size="8">
                      <svg
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        :stroke="t.rls_enabled ? 'currentColor' : '#d03050'"
                        stroke-width="2"
                        :stroke-dasharray="t.rls_enabled ? undefined : '4 2'"
                      >
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                      </svg>
                      <NTag
                        :type="t.rls_enabled ? 'success' : 'error'"
                        size="small"
                      >
                        {{ t.rls_enabled ? 'RLS on' : 'RLS off' }}
                      </NTag>
                    </NSpace>
                  </template>
                </NThing>
              </NListItem>
            </NList>
            <EmptyState
              v-else-if="tables && tables.length === 0"
              description="No tables in this schema."
            />
          </template>
          <NEmpty v-else description="Select a schema to view its tables." />
        </NSpin>
      </NCard>
    </NLayoutContent>
  </NLayout>
</template>

<style scoped>
.schema-active {
  background-color: rgba(16, 185, 129, 0.08);
}
</style>
