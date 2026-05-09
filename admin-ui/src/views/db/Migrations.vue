<script setup lang="ts">
import { ref, computed } from "vue";
import { NCard, NDataTable, NText, NSpin, NSelect, NSpace } from "naive-ui";
import type { DataTableColumn } from "naive-ui";
import EmptyState from "@/components/feedback/EmptyState.vue";
import ErrorState from "@/components/feedback/ErrorState.vue";
import { useResource } from "@/composables/useResource";
import { dbApi } from "@/api/resources";

interface Migration {
    version: string;
    applied_at: string | null;
    source: string;
}

const sourceFilter = ref<string | null>(null);

const sourceFilterOptions = [
    { label: "All sources", value: null },
    { label: "supython", value: "supython" },
    { label: "dbmate", value: "dbmate" },
] as any[];

const {
    data: migrations,
    error,
    loading,
    refresh,
} = useResource(() => dbApi.migrations());

const hasDbmate = computed(() =>
    (migrations.value ?? []).some((m) => m.source === "dbmate"),
);

const filteredMigrations = computed(() => {
    const all = migrations.value ?? [];
    if (!sourceFilter.value) return all;
    return all.filter((m) => m.source === sourceFilter.value);
});

const columns: DataTableColumn<Migration>[] = [
    {
        title: "Version",
        key: "version",
        sorter: (a: Migration, b: Migration) =>
            a.version.localeCompare(b.version),
        defaultSortOrder: "ascend" as const,
    },
    { title: "Source", key: "source", width: 120 },
    {
        title: "Applied at",
        key: "applied_at",
        width: 220,
        render: (row: Migration) => {
            if (!row.applied_at) return "—";
            return new Date(row.applied_at).toLocaleString();
        },
    },
];

function rowKey(row: Migration): string {
    return `${row.source}:${row.version}`;
}
</script>

<template>
    <NCard title="Migrations">
        <NSpace vertical :size="16">
            <!-- Toolbar -->
            <NSpace align="center" justify="space-between">
                <NSelect
                    v-model:value="sourceFilter"
                    :options="sourceFilterOptions"
                    style="width: 160px"
                />
                <NText depth="3" style="font-size: 12px">
                    {{ filteredMigrations.length }} migration{{
                        filteredMigrations.length === 1 ? "" : "s"
                    }}
                </NText>
            </NSpace>

            <NSpin :show="loading">
                <ErrorState :error="error" :retry="refresh" />

                <template v-if="migrations && migrations.length > 0">
                    <NDataTable
                        :columns="columns"
                        :data="filteredMigrations"
                        :row-key="rowKey"
                        :bordered="false"
                        size="small"
                    />

                    <!-- dbmate-absent empty-state -->
                    <template v-if="!hasDbmate">
                        <EmptyState
                            description="dbmate not detected — install it to track app‑level migrations.  See docs/migrations.md for setup."
                        />
                    </template>
                </template>

                <EmptyState
                    v-else-if="migrations && migrations.length === 0"
                    description="No migrations recorded. Run supython migrate to apply framework migrations."
                />
            </NSpin>
        </NSpace>
    </NCard>
</template>
