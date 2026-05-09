<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
    NCard,
    NSpace,
    NSelect,
    NButton,
    NInput,
    NTag,
    NText,
    NSpin,
    NAlert,
    NDivider,
} from "naive-ui";
import EmptyState from "@/components/feedback/EmptyState.vue";
import ErrorState from "@/components/feedback/ErrorState.vue";
import CodeViewer from "@/components/editors/CodeViewer.vue";
import { useResource } from "@/composables/useResource";
import { functionsApi } from "@/api/resources";
import type { FunctionInvokeResponse } from "@/api/types";

const route = useRoute();
const routeName = computed(() => route.params.name as string);

const {
    data: routes,
    error: routesError,
    loading: routesLoading,
} = useResource(() => functionsApi.routes());

const selectedRoute = computed(
    () => routes.value?.find((r) => r.name === routeName.value) ?? null,
);

const method = ref<string>("POST");
watch(selectedRoute, (r) => {
    if (r && r.methods.length > 0 && !r.methods.includes(method.value)) {
        method.value = r.methods[0];
    }
});

const methodOptions = computed(
    () =>
        selectedRoute.value?.methods.map((m) => ({ label: m, value: m })) ?? [],
);

const headersText = ref("{}");
const bodyText = ref("");

const running = ref(false);
const response = ref<FunctionInvokeResponse | null>(null);
const runError = ref<string | null>(null);

const statusTagType = computed(() => {
    if (!response.value) return "default";
    const s = response.value.status;
    if (s >= 200 && s < 300) return "success";
    if (s >= 400) return "error";
    return "warning";
});

async function run() {
    running.value = true;
    response.value = null;
    runError.value = null;

    let headers: Record<string, string> = {};
    try {
        if (headersText.value.trim()) {
            headers = JSON.parse(headersText.value);
        }
    } catch {
        runError.value = "Headers must be valid JSON";
        running.value = false;
        return;
    }

    let body: unknown = null;
    if (bodyText.value.trim()) {
        try {
            body = JSON.parse(bodyText.value);
        } catch {
            body = bodyText.value;
        }
    }

    try {
        const res = await functionsApi.invoke(routeName.value, {
            method: method.value,
            headers,
            body,
        });
        response.value = res;
    } catch (e: unknown) {
        runError.value = (e as { message?: string }).message ?? "Invoke failed";
    } finally {
        running.value = false;
    }
}
</script>

<template>
    <NCard :title="`Invoke: ${routeName}`" size="small">
        <NSpin :show="routesLoading">
            <ErrorState :error="routesError" :retry="() => {}" />
            <template v-if="selectedRoute">
                <NSpace vertical :size="16">
                    <NAlert
                        v-if="selectedRoute.auth === 'authenticated'"
                        type="warning"
                        :show-icon="true"
                    >
                        This function expects an end-user JWT. Admin invoke runs
                        under
                        <code>service_role</code>; RLS is bypassed.
                    </NAlert>

                    <NSpace align="center" :size="12">
                        <NSelect
                            v-model:value="method"
                            :options="methodOptions"
                            style="width: 120px"
                        />
                        <NButton type="primary" :loading="running" @click="run">
                            Run
                        </NButton>
                    </NSpace>

                    <div>
                        <NText
                            strong
                            style="display: block; margin-bottom: 6px"
                        >
                            Headers (JSON)
                        </NText>
                        <NInput
                            v-model:value="headersText"
                            type="textarea"
                            :rows="3"
                            placeholder='{"Content-Type": "application/json"}'
                        />
                    </div>

                    <div>
                        <NText
                            strong
                            style="display: block; margin-bottom: 6px"
                        >
                            Body
                        </NText>
                        <CodeViewer
                            v-model="bodyText"
                            :read-only="false"
                            height="200px"
                        />
                    </div>

                    <NDivider />

                    <template v-if="response">
                        <NSpace
                            align="center"
                            :size="12"
                            style="margin-bottom: 8px"
                        >
                            <NTag :type="statusTagType">{{
                                response.status
                            }}</NTag>
                            <NText depth="3" style="font-size: 12px">
                                {{ response.elapsed_ms.toFixed(2) }} ms
                            </NText>
                        </NSpace>

                        <NText
                            strong
                            style="display: block; margin-bottom: 6px"
                        >
                            Response headers
                        </NText>
                        <pre
                            style="
                                background: var(--n-code-color);
                                padding: 12px;
                                border-radius: 4px;
                                font-size: 12px;
                                overflow-x: auto;
                            "
                            >{{
                                JSON.stringify(response.headers, null, 2)
                            }}</pre
                        >

                        <NText
                            strong
                            style="display: block; margin: 12px 0 6px"
                        >
                            Response body
                        </NText>
                        <pre
                            v-if="response.body !== null"
                            style="
                                background: var(--n-code-color);
                                padding: 12px;
                                border-radius: 4px;
                                font-size: 12px;
                                overflow-x: auto;
                            "
                            >{{ JSON.stringify(response.body, null, 2) }}</pre
                        >
                        <pre
                            v-else-if="response.body_text"
                            style="
                                background: var(--n-code-color);
                                padding: 12px;
                                border-radius: 4px;
                                font-size: 12px;
                                overflow-x: auto;
                            "
                            >{{ response.body_text }}</pre
                        >
                        <EmptyState v-else description="Empty response body." />
                    </template>

                    <ErrorState
                        v-if="runError"
                        :error="{ message: runError }"
                        :retry="run"
                    />

                    <EmptyState
                        v-if="!response && !runError && !running"
                        description="Choose a method, edit headers/body, and press Run."
                    />
                </NSpace>
            </template>
            <EmptyState
                v-else-if="!routesLoading"
                description="Function not found."
            />
        </NSpin>
    </NCard>
</template>
