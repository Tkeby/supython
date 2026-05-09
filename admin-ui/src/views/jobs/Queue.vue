<script setup lang="ts">
import { computed, h, ref } from "vue";
import {
    NButton,
    NCard,
    NDataTable,
    NDescriptions,
    NDescriptionsItem,
    NDrawer,
    NDrawerContent,
    NDivider,
    NPagination,
    NSpace,
    NTag,
    NText,
} from "naive-ui";
import type { DataTableColumn } from "naive-ui";
import ResourceTable from "@/components/data/ResourceTable.vue";
import JsonField from "@/components/data/JsonField.vue";
import EmptyState from "@/components/feedback/EmptyState.vue";
import type { FilterDef } from "@/components/data/filters/types";
import { useTable } from "@/composables/useTable";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import { jobsApi } from "@/api/resources";
import type { AdminJobRow, AdminJobsPage, JobStatus } from "@/api/types";

const toast = useToast();
const confirm = useConfirm();

// ── Status helpers ───────────────────────────────────────────────
const STATUS_COLORS: Record<
    JobStatus,
    "warning" | "info" | "success" | "error" | "default"
> = {
    queued: "warning",
    running: "info",
    succeeded: "success",
    failed: "error",
    cancelled: "default",
};

const STATUS_OPTIONS: { label: string; value: string }[] = [
    { label: "Any", value: "" },
    { label: "Queued", value: "queued" },
    { label: "Running", value: "running" },
    { label: "Succeeded", value: "succeeded" },
    { label: "Failed", value: "failed" },
    { label: "Cancelled", value: "cancelled" },
];

// ── Table ────────────────────────────────────────────────────────
interface JobFilters {
    status: string | null;
}

const filterDefs: FilterDef[] = [
    {
        type: "select",
        key: "status",
        label: "Status",
        options: STATUS_OPTIONS.map((o) => ({
            label: o.label,
            value: o.value || null,
        })),
        clearable: true,
    },
];

const { q, data, loading, error, refresh } = useTable<AdminJobRow, JobFilters>(
    (q) =>
        jobsApi.queue({
            status: (q.filters.status as JobStatus) || undefined,
            limit: q.limit,
            offset: q.offset,
        }),
    { status: null },
);

// ``useTable`` narrows the return type to ``{ rows, total }`` but the
// backend returns ``AdminJobsPage`` which also includes ``counts``.
const page = computed(() => data.value as AdminJobsPage | null);
const rows = computed(() => page.value?.rows ?? []);
const total = computed(() => page.value?.total ?? 0);
const counts = computed(() => page.value?.counts ?? {});

function fmtDate(v: string | null): string {
    return v ? new Date(v).toLocaleString() : "—";
}

const columns: DataTableColumn<AdminJobRow>[] = [
    { title: "Name", key: "name", ellipsis: { tooltip: true } },
    {
        title: "Status",
        key: "status",
        width: 120,
        render: (row) =>
            h(
                NTag,
                { type: STATUS_COLORS[row.status], size: "small" },
                { default: () => row.status },
            ),
    },
    { title: "Queue", key: "queue", width: 120 },
    {
        title: "Attempts",
        key: "attempts",
        width: 100,
        render: (row) => `${row.attempts}/${row.max_attempts}`,
    },
    {
        title: "Created",
        key: "created_at",
        width: 160,
        render: (row) => fmtDate(row.created_at),
    },
    {
        title: "Finished",
        key: "finished_at",
        width: 160,
        render: (row) => fmtDate(row.finished_at),
    },
];

// ── Drawer ───────────────────────────────────────────────────────
const drawerOpen = ref(false);
const selectedJob = ref<AdminJobRow | null>(null);

function openDrawer(job: AdminJobRow) {
    selectedJob.value = job;
    drawerOpen.value = true;
}

function closeDrawer() {
    drawerOpen.value = false;
    selectedJob.value = null;
}

// ── Actions ──────────────────────────────────────────────────────
async function handleRetry() {
    if (!selectedJob.value) return;
    const ok = await confirm(
        `Retry job "${selectedJob.value.name}"?`,
        "The job will be re-queued for execution.",
    );
    if (!ok) return;
    try {
        await jobsApi.retry(selectedJob.value.id);
        toast.success("Job re-queued.");
        closeDrawer();
        await refresh();
    } catch (e: unknown) {
        toast.error((e as { message?: string }).message ?? "Retry failed");
    }
}

async function handleCancel() {
    if (!selectedJob.value) return;
    const ok = await confirm(
        `Cancel job "${selectedJob.value.name}"?`,
        "The job will be marked as cancelled.",
    );
    if (!ok) return;
    try {
        await jobsApi.cancel(selectedJob.value.id);
        toast.success("Job cancelled.");
        closeDrawer();
        await refresh();
    } catch (e: unknown) {
        toast.error((e as { message?: string }).message ?? "Cancel failed");
    }
}
</script>

<template>
    <NCard title="Job Queue" size="small">
        <!-- Per-status count chips -->
        <NSpace :size="8" style="margin-bottom: 12px">
            <NTag
                v-for="opt in STATUS_OPTIONS.filter((o) => o.value)"
                :key="opt.value"
                :type="STATUS_COLORS[opt.value as JobStatus]"
                size="small"
                round
            >
                {{ opt.label }}:
                {{ counts[opt.value] ?? 0 }}
            </NTag>
        </NSpace>

        <!-- Table area -->
        <ResourceTable
            :q="q"
            :rows="rows"
            :total="total"
            :loading="loading"
            :error="error"
            :columns="columns"
            :filters="filterDefs"
            @refresh="refresh"
        >
            <template #default>
                <NDataTable
                    :columns="columns"
                    :data="rows"
                    :bordered="false"
                    :row-props="
                        (row: AdminJobRow) => ({
                            style: 'cursor: pointer',
                            onClick: () => openDrawer(row),
                        })
                    "
                />
                <NPagination
                    :page="Math.floor(q.offset / q.limit) + 1"
                    :page-count="Math.max(1, Math.ceil(total / q.limit))"
                    style="margin-top: 12px"
                    @update:page="(p: number) => (q.offset = (p - 1) * q.limit)"
                />
            </template>
        </ResourceTable>

        <!-- Drawer -->
        <NDrawer
            :show="drawerOpen"
            :width="560"
            placement="right"
            :mask-closable="true"
            @update:show="
                (v: boolean) => {
                    if (!v) closeDrawer();
                }
            "
        >
            <NDrawerContent title="Job detail" closable @close="closeDrawer">
                <template v-if="selectedJob">
                    <!-- Actions -->
                    <NSpace style="margin-bottom: 20px">
                        <NButton
                            v-if="
                                selectedJob.status === 'failed' ||
                                selectedJob.status === 'cancelled'
                            "
                            type="warning"
                            size="small"
                            @click="handleRetry"
                        >
                            Retry
                        </NButton>
                        <NButton
                            v-if="selectedJob.status === 'queued'"
                            type="error"
                            size="small"
                            secondary
                            @click="handleCancel"
                        >
                            Cancel
                        </NButton>
                    </NSpace>

                    <!-- Job record -->
                    <NDescriptions
                        bordered
                        label-placement="top"
                        :column="1"
                        size="small"
                    >
                        <NDescriptionsItem label="id">
                            <NText code>{{ selectedJob.id }}</NText>
                        </NDescriptionsItem>
                        <NDescriptionsItem label="name">
                            {{ selectedJob.name }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="version">
                            {{ selectedJob.version }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="status">
                            <NTag
                                :type="STATUS_COLORS[selectedJob.status]"
                                size="small"
                            >
                                {{ selectedJob.status }}
                            </NTag>
                        </NDescriptionsItem>
                        <NDescriptionsItem label="queue">
                            {{ selectedJob.queue }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="role">
                            {{ selectedJob.role }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="attempts">
                            {{ selectedJob.attempts }} /
                            {{ selectedJob.max_attempts }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="user_id">
                            {{ selectedJob.user_id ?? "—" }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="run_at">
                            {{ fmtDate(selectedJob.run_at) }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="locked_at">
                            {{ fmtDate(selectedJob.locked_at) }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="locked_by">
                            {{ selectedJob.locked_by ?? "—" }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="created_at">
                            {{ fmtDate(selectedJob.created_at) }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="finished_at">
                            {{ fmtDate(selectedJob.finished_at) }}
                        </NDescriptionsItem>
                    </NDescriptions>

                    <NDivider />

                    <NText strong style="display: block; margin-bottom: 8px">
                        Payload
                    </NText>
                    <JsonField :value="selectedJob.payload" />
                    <EmptyState
                        v-if="!selectedJob.payload"
                        description="No payload."
                    />

                    <template v-if="selectedJob.last_error">
                        <NDivider />
                        <NText
                            strong
                            style="display: block; margin-bottom: 8px"
                        >
                            Last Error
                        </NText>
                        <NText
                            type="error"
                            style="white-space: pre-wrap; font-size: 13px"
                        >
                            {{ selectedJob.last_error }}
                        </NText>
                    </template>
                </template>
            </NDrawerContent>
        </NDrawer>
    </NCard>
</template>
