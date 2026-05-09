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
  NButton,
  NText,
} from 'naive-ui'
import EmptyState from '@/components/feedback/EmptyState.vue'
import ErrorState from '@/components/feedback/ErrorState.vue'
import CodeViewer from '@/components/editors/CodeViewer.vue'
import { useResource } from '@/composables/useResource'
import { functionsApi } from '@/api/resources'
import type { FunctionRoute } from '@/api/types'

const router = useRouter()
const selectedRoute = ref<FunctionRoute | null>(null)

const {
  data: routes,
  error: routesError,
  loading: routesLoading,
  refresh: refreshRoutes,
} = useResource(() => functionsApi.routes())

const {
  data: source,
  error: sourceError,
  loading: sourceLoading,
  refresh: refreshSource,
} = useResource(
  () =>
    selectedRoute.value
      ? functionsApi.source(selectedRoute.value.name)
      : Promise.resolve(null),
  () => [selectedRoute.value?.name],
)

function selectRoute(route: FunctionRoute) {
  selectedRoute.value = route
}

function goToInvoke(route: FunctionRoute) {
  router.push(`/functions/invoke/${encodeURIComponent(route.name)}`)
}
</script>

<template>
  <NLayout has-sider style="height: calc(100vh - 112px)">
    <NLayoutSider bordered width="300" :native-scrollbar="false">
      <NCard title="Routes" :bordered="false" size="small">
        <NSpin :show="routesLoading">
          <ErrorState :error="routesError" :retry="refreshRoutes" />
          <NList v-if="routes && routes.length > 0" hoverable clickable>
            <NListItem
              v-for="r in routes"
              :key="r.name"
              :class="{ 'route-active': selectedRoute?.name === r.name }"
              @click="selectRoute(r)"
            >
              <NThing :title="r.name">
                <template #description>
                  <NSpace :size="4">
                    <NTag
                      v-for="m in r.methods"
                      :key="m"
                      size="tiny"
                      type="info"
                    >
                      {{ m }}
                    </NTag>
                    <NTag
                      :type="r.auth === 'authenticated' ? 'warning' : 'default'"
                      size="tiny"
                    >
                      {{ r.auth }}
                    </NTag>
                  </NSpace>
                </template>
                <template #header-extra>
                  <NButton size="tiny" @click.stop="goToInvoke(r)">
                    Invoke
                  </NButton>
                </template>
              </NThing>
            </NListItem>
          </NList>
          <EmptyState
            v-else-if="routes && routes.length === 0"
            description="No functions discovered."
          />
        </NSpin>
      </NCard>
    </NLayoutSider>

    <NLayoutContent style="padding: 16px 24px" :native-scrollbar="false">
      <NCard
        :title="selectedRoute ? selectedRoute.name : 'Source'"
        :bordered="false"
        size="small"
      >
        <NSpin :show="sourceLoading">
          <ErrorState :error="sourceError" :retry="refreshSource" />
          <template v-if="source">
            <NSpace
              align="center"
              :size="12"
              style="margin-bottom: 12px"
            >
              <NText depth="3" style="font-size: 12px">
                {{ source.path }}
              </NText>
              <NTag size="small">{{ source.size }} bytes</NTag>
            </NSpace>
            <CodeViewer
              :model-value="source.source"
              :read-only="true"
              :height="'calc(100vh - 260px)'"
            />
          </template>
          <EmptyState
            v-else-if="!selectedRoute"
            description="Select a route to view its source."
          />
        </NSpin>
      </NCard>
    </NLayoutContent>
  </NLayout>
</template>

<style scoped>
.route-active {
  background-color: rgba(16, 185, 129, 0.08);
}
</style>
