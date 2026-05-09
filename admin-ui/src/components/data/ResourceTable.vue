<script setup lang="ts" generic="Row extends Record<string, unknown>, F extends object = Record<string, never>">
import { computed } from "vue";
import { NDataTable, NPagination, NSpin } from "naive-ui";
import type { DataTableColumn } from "naive-ui";
import type { TableQuery } from "@/composables/useTable";
import type { FilterDef, FilterValues } from "./filters/types";
import ErrorState from "@/components/feedback/ErrorState.vue";
import FilterBar from "./FilterBar.vue";
import EmptyState from "../feedback/EmptyState.vue";

const props = defineProps<{
    q: TableQuery<F>;
    rows: Row[] | null;
    total: number;
    loading: boolean;
    error: { message: string } | null;
    columns: DataTableColumn<Row>[];
    searchPlaceholder?: string;
    filters?: FilterDef[];
}>();
const emit = defineEmits<{ (e: "refresh"): void }>();

function refresh() {
    emit("refresh");
}

const page = computed({
    get: () => Math.floor(props.q.offset / props.q.limit) + 1,
    set: (v) => {
        props.q.offset = (v - 1) * props.q.limit;
    },
});
</script>

<template>
    <FilterBar
        v-model:search="q.search"
        v-model:values="(q.filters as FilterValues)"
        :filters="filters"
        :placeholder="searchPlaceholder"
        @refresh="emit('refresh')"
    />
    <ErrorState :error="error" :retry="refresh" />

    <NSpin :show="loading">
        <slot>
            <NDataTable :columns="columns" :data="rows ?? []" :bordered="false">
                <template #empty>
                    <EmptyState
                        description="No rows visible under this role. RLS may be hiding rows that exist."
                    />
                </template>
            </NDataTable>
            <NPagination
                v-model:page="page"
                :page-count="Math.max(1, Math.ceil(total / q.limit))"
                style="margin-top: 12px"
            />
        </slot>
    </NSpin>
</template>
