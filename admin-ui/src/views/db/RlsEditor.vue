<script setup lang="ts">
import { ref, computed, watch } from "vue";
import {
    NCard,
    NSpace,
    NSelect,
    NDataTable,
    NSpin,
    NTag,
    NText,
    NDivider,
} from "naive-ui";
import EmptyState from "@/components/feedback/EmptyState.vue";
import ErrorState from "@/components/feedback/ErrorState.vue";
import RlsPolicyEditor from "@/components/editors/RlsPolicyEditor.vue";
import { useToast } from "@/composables/useToast";
import { dbApi } from "@/api/resources";
import type { RlsPolicy, SqlResult } from "@/api/types";

const toast = useToast();

const schemas = ref<{ label: string; value: string }[]>([]);
const tables = ref<{ label: string; value: string }[]>([]);
const selectedSchema = ref<string | null>(null);
const selectedTable = ref<string | null>(null);

const policiesLoading = ref(false);
const policiesError = ref<{ message: string } | null>(null);
const policies = ref<RlsPolicy[] | null>(null);

const ddl = ref("");
const sampleQuery = ref("");
const running = ref(false);

const beforeResult = ref<SqlResult | null>(null);
const afterResult = ref<SqlResult | null>(null);
const dryRunError = ref<string | null>(null);

async function loadSchemas() {
    try {
        const rows = await dbApi.schemas();
        schemas.value = rows.map((s) => ({ label: s.name, value: s.name }));
    } catch (e: any) {
        toast.error(e.message ?? "Failed to load schemas");
    }
}

async function loadTables(schema: string) {
    try {
        const rows = await dbApi.tables(schema);
        tables.value = rows.map((t) => ({ label: t.name, value: t.name }));
    } catch (e: any) {
        toast.error(e.message ?? "Failed to load tables");
    }
}

async function loadPolicies() {
    if (!selectedSchema.value || !selectedTable.value) return;
    policiesLoading.value = true;
    policiesError.value = null;
    policies.value = null;
    try {
        policies.value = await dbApi.policies(
            selectedSchema.value,
            selectedTable.value,
        );
    } catch (e: any) {
        policiesError.value = {
            message: e.message ?? "Failed to load policies",
        };
    } finally {
        policiesLoading.value = false;
    }
}

watch(selectedSchema, (schema) => {
    selectedTable.value = null;
    policies.value = null;
    tables.value = [];
    if (schema) loadTables(schema);
});

watch(selectedTable, (table) => {
    policies.value = null;
    beforeResult.value = null;
    afterResult.value = null;
    dryRunError.value = null;
    if (table) loadPolicies();
});

loadSchemas();

const policyColumns = [
    { title: "Name", key: "policyname" },
    { title: "Command", key: "cmd" },
    { title: "Permissive", key: "permissive" },
    {
        title: "Roles",
        key: "roles",
        render: (row: RlsPolicy) => row.roles?.join(", ") ?? "*",
    },
    {
        title: "USING",
        key: "qual",
        render: (row: RlsPolicy) => row.qual ?? "—",
    },
    {
        title: "WITH CHECK",
        key: "with_check",
        render: (row: RlsPolicy) => row.with_check ?? "—",
    },
];

const beforeCount = computed(() => beforeResult.value?.row_count ?? null);
const afterCount = computed(() => afterResult.value?.row_count ?? null);
const countChanged = computed(
    () =>
        beforeCount.value !== null &&
        afterCount.value !== null &&
        beforeCount.value !== afterCount.value,
);

async function runDryRun() {
    if (!selectedSchema.value || !selectedTable.value) {
        toast.warning("Select a schema and table first");
        return;
    }
    const sql = sampleQuery.value.trim();
    const policyDdl = ddl.value.trim();
    if (!sql || !policyDdl) {
        toast.warning("Enter both DDL and a sample query");
        return;
    }

    running.value = true;
    beforeResult.value = null;
    afterResult.value = null;
    dryRunError.value = null;

    try {
        // Baseline: run sample query without the DDL
        beforeResult.value = await dbApi.runSql(sql, true);
    } catch (e: any) {
        dryRunError.value = `Baseline query failed: ${e.message ?? "Unknown error"}`;
        toast.error(dryRunError.value);
        running.value = false;
        return;
    }

    try {
        // Dry-run: apply DDL in rollback transaction
        const res = await dbApi.dryRunPolicy(policyDdl, sql);
        afterResult.value = {
            columns: res.columns,
            rows: res.rows,
            row_count: res.rows.length,
        };
    } catch (e: any) {
        dryRunError.value = e.message ?? "Dry-run failed";
        toast.error(dryRunError.value as any);
    } finally {
        running.value = false;
    }
}

const resultColumns = computed(() =>
    afterResult.value
        ? afterResult.value.columns.map((c) => ({ title: c, key: c }))
        : [],
);

const resultRows = computed(() => {
    if (!afterResult.value) return [];
    return afterResult.value.rows.map((row) =>
        Object.fromEntries(
            afterResult.value!.columns.map((col, i) => {
                const val = row[i];
                let text: string;
                if (val === null) text = "null";
                else if (typeof val === "object") text = JSON.stringify(val);
                else text = String(val);
                return [col, text];
            }),
        ),
    );
});
</script>

<template>
    <NCard title="RLS Policies">
        <NSpace vertical :size="24">
            <!-- Selectors -->
            <NSpace align="center" :size="12">
                <NSelect
                    v-model:value="selectedSchema"
                    :options="schemas"
                    placeholder="Select schema"
                    style="width: 200px"
                />
                <NSelect
                    v-model:value="selectedTable"
                    :options="tables"
                    placeholder="Select table"
                    style="width: 200px"
                    :disabled="!selectedSchema"
                />
            </NSpace>

            <!-- Policies list -->
            <NSpin :show="policiesLoading">
                <ErrorState :error="policiesError" :retry="loadPolicies" />
                <template
                    v-if="selectedTable && !policiesLoading && !policiesError"
                >
                    <NText
                        depth="3"
                        style="
                            font-size: 12px;
                            margin-bottom: 8px;
                            display: block;
                        "
                    >
                        Policies on {{ selectedSchema }}.{{ selectedTable }}
                    </NText>
                    <NDataTable
                        v-if="policies && policies.length > 0"
                        :columns="policyColumns"
                        :data="policies"
                        :bordered="false"
                        size="small"
                    />
                    <EmptyState
                        v-else
                        description="No policies defined on this table."
                    />
                </template>
            </NSpin>

            <NDivider />

            <!-- Dry-run editor -->
            <div>
                <NText
                    strong
                    style="font-size: 16px; display: block; margin-bottom: 12px"
                >
                    Dry-run policy change
                </NText>
                <RlsPolicyEditor
                    v-model:ddl="ddl"
                    v-model:sample-query="sampleQuery"
                    :running="running"
                    @run="runDryRun"
                />
            </div>

            <!-- Results -->
            <div v-if="beforeResult || afterResult || dryRunError">
                <ErrorState
                    :error="dryRunError ? { message: dryRunError } : null"
                />
                <template v-if="!dryRunError && afterResult">
                    <NSpace
                        align="center"
                        :size="12"
                        style="margin-bottom: 12px"
                    >
                        <NTag size="small">Before: {{ beforeCount }} rows</NTag>
                        <NTag
                            :type="countChanged ? 'warning' : 'success'"
                            size="small"
                        >
                            After: {{ afterCount }} rows
                        </NTag>
                        <NTag v-if="countChanged" type="warning" size="small">
                            Would change behavior
                        </NTag>
                        <NTag v-else type="success" size="small">
                            No change
                        </NTag>
                    </NSpace>
                    <NDataTable
                        v-if="resultRows.length"
                        :columns="resultColumns"
                        :data="resultRows"
                        :bordered="false"
                        size="small"
                        :scroll-x="600"
                    />
                    <EmptyState v-else description="Query returned no rows." />
                </template>
            </div>
        </NSpace>
    </NCard>
</template>
