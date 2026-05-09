<script setup lang="ts">
import { computed, h, ref } from "vue";
import {
    NCard,
    NDataTable,
    NDescriptions,
    NDescriptionsItem,
    NDrawer,
    NDrawerContent,
    NPagination,
    NSpace,
    NTag,
    NText,
} from "naive-ui";
import type { DataTableColumn } from "naive-ui";
import ResourceTable from "@/components/data/ResourceTable.vue";
import JsonField from "@/components/data/JsonField.vue";
import type { FilterDef } from "@/components/data/filters/types";
import { useTable } from "@/composables/useTable";
import { authApi } from "@/api/resources";
import type { AdminAuditEvent } from "@/api/types";

interface AuditFilters {
    event: string | null;
    ip: string | null;
    from: string | null;
    to: string | null;
}

const filterDefs: FilterDef[] = [
    {
        type: "text",
        key: "event",
        label: "Event",
        placeholder: "e.g. login, signup",
        debounceMs: 300,
        width: 200,
    },
    {
        type: "text",
        key: "ip",
        label: "IP",
        placeholder: "e.g. 192.168",
        debounceMs: 300,
        width: 160,
    },
    {
        type: "date",
        key: "from",
        label: "From",
        width: 160,
    },
    {
        type: "date",
        key: "to",
        label: "To",
        width: 160,
    },
];

const { q, data, loading, error, refresh } = useTable<
    AdminAuditEvent,
    AuditFilters
>(
    (q) =>
        authApi.audit({
            event: q.filters.event || undefined,
            ip: q.filters.ip || undefined,
            from_date: q.filters.from || undefined,
            to_date: q.filters.to || undefined,
            limit: q.limit,
            offset: q.offset,
        }),
    { event: null, ip: null, from: null, to: null },
);

const rows = computed(() => data.value?.rows ?? []);
const total = computed(() => data.value?.total ?? 0);

const columns: DataTableColumn<AdminAuditEvent>[] = [
    {
        title: "Time",
        key: "created_at",
        width: 170,
        render: (row) => new Date(row.created_at).toLocaleString(),
    },
    {
        title: "Actor",
        key: "user_id",
        width: 320,
        render: (row) => (row.user_id ? row.user_id : "—"),
        ellipsis: { tooltip: true },
    },
    {
        title: "Event",
        key: "event",
        width: 160,
        render: (row) =>
            h(
                NTag,
                { type: "info", size: "small" },
                { default: () => row.event },
            ),
    },
    {
        title: "IP",
        key: "ip",
        width: 130,
        render: (row) => row.ip ?? "—",
    },
    {
        title: "UA",
        key: "ua",
        width: 200,
        ellipsis: { tooltip: true },
        render: (row) =>
            row.ua
                ? row.ua.slice(0, 40) + (row.ua.length > 40 ? "…" : "")
                : "—",
    },
];

// ── Drawer ───────────────────────────────────────────────────────
const drawerOpen = ref(false);
const selectedRow = ref<AdminAuditEvent | null>(null);

function openDrawer(row: AdminAuditEvent) {
    selectedRow.value = row;
    drawerOpen.value = true;
}

function closeDrawer() {
    drawerOpen.value = false;
    selectedRow.value = null;
}
</script>

<template>
    <NCard title="Audit Log" size="small">
        <NSpace vertical :size="16">
            <ResourceTable
                :q="q"
                :rows="rows"
                :total="total"
                :loading="loading"
                :error="error"
                :columns="columns"
                :filters="filterDefs"
                search-placeholder="Filter rows…"
                @refresh="refresh"
            >
                <template #default>
                    <NDataTable
                        :columns="columns"
                        :data="rows"
                        :bordered="false"
                        :row-props="
                            (row: AdminAuditEvent) => ({
                                style: 'cursor: pointer',
                                onClick: () => openDrawer(row),
                            })
                        "
                    />
                    <NPagination
                        :page="Math.floor(q.offset / q.limit) + 1"
                        :page-count="Math.max(1, Math.ceil(total / q.limit))"
                        style="margin-top: 12px"
                        @update:page="
                            (p: number) => (q.offset = (p - 1) * q.limit)
                        "
                    />
                </template>
            </ResourceTable>
        </NSpace>

        <!-- Drawer for full payload -->
        <NDrawer
            :show="drawerOpen"
            :width="520"
            placement="right"
            :mask-closable="true"
            @update:show="
                (v: boolean) => {
                    if (!v) closeDrawer();
                }
            "
        >
            <NDrawerContent
                :title="
                    selectedRow ? `Event: ${selectedRow.event}` : 'Event detail'
                "
                closable
                @close="closeDrawer"
            >
                <template v-if="selectedRow">
                    <NDescriptions
                        bordered
                        label-placement="top"
                        :column="1"
                        size="small"
                        style="margin-bottom: 16px"
                    >
                        <NDescriptionsItem label="ID">
                            <NText code>{{ selectedRow.id }}</NText>
                        </NDescriptionsItem>
                        <NDescriptionsItem label="Event">
                            {{ selectedRow.event }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="Actor (user_id)">
                            {{ selectedRow.user_id ?? "—" }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="Time">
                            {{
                                new Date(
                                    selectedRow.created_at,
                                ).toLocaleString()
                            }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="IP">
                            {{ selectedRow.ip ?? "—" }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="User-Agent">
                            {{ selectedRow.ua ?? "—" }}
                        </NDescriptionsItem>
                    </NDescriptions>

                    <NText strong style="display: block; margin-bottom: 8px">
                        Payload
                    </NText>
                    <JsonField :value="selectedRow.payload" />
                </template>
                <template v-else>
                    <NText depth="3"
                        >Click a row to see full event details.</NText
                    >
                </template>
            </NDrawerContent>
        </NDrawer>
    </NCard>
</template>
