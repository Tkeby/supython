<script setup lang="ts">
import { h } from "vue";
import { NCard, NDataTable, NTag, NText } from "naive-ui";
import type { DataTableColumn } from "naive-ui";
import EmptyState from "@/components/feedback/EmptyState.vue";
import ErrorState from "@/components/feedback/ErrorState.vue";
import { NSpin } from "naive-ui";
import { useResource } from "@/composables/useResource";
import { realtimeApi } from "@/api/resources";
import type { EnabledTable } from "@/api/types";

const {
    data: tables,
    loading,
    error,
    refresh,
} = useResource(() => realtimeApi.tables());

const columns: DataTableColumn<EnabledTable>[] = [
    {
        title: "Schema",
        key: "schema_name",
        width: 140,
    },
    {
        title: "Table",
        key: "table_name",
        width: 200,
    },
    {
        title: "Primary Key",
        key: "pk_columns",
        width: 180,
        render: (row) =>
            row.pk_columns.length
                ? h(
                      NTag,
                      { size: "small", type: "info", bordered: false },
                      { default: () => row.pk_columns.join(", ") },
                  )
                : h(NText, { depth: 3 }, { default: () => "—" }),
    },
    {
        title: "Owner Column",
        key: "owner_column",
        width: 140,
        render: (row) =>
            row.owner_column ?? h(NText, { depth: 3 }, { default: () => "—" }),
    },
    {
        title: "Enabled At",
        key: "created_at",
        width: 170,
        render: (row) => new Date(row.created_at).toLocaleString(),
    },
];
</script>

<template>
    <NCard title="Enabled Tables" size="small">
        <ErrorState :error="error" :retry="refresh" />
        <NSpin :show="loading">
            <NDataTable
                v-if="tables && tables.length > 0"
                :columns="columns"
                :data="tables"
                :bordered="false"
                size="small"
            />
            <EmptyState
                v-else-if="tables && tables.length === 0"
                description="No tables are realtime-enabled. Enable tables via SQL migrations."
            />
        </NSpin>
    </NCard>
</template>
