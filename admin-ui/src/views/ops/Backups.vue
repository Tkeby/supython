<script setup lang="ts">
import { computed, h, onUnmounted, ref, watch } from "vue";
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
import { useTable } from "@/composables/useTable";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import { opsApi } from "@/api/resources";
import type { AdminBackupRow } from "@/api/types";

const toast = useToast();
const confirm = useConfirm();

// ── Status helpers ───────────────────────────────────────────────
const STATUS_COLORS: Record<
    string,
    "info" | "success" | "error" | "warning" | "default"
> = {
    running: "info",
    completed: "success",
    failed: "error",
    pending: "warning",
};

function fmtDate(v: string | null): string {
    return v ? new Date(v).toLocaleString() : "—";
}

function fmtBytes(v: number | null): string {
    if (v === null || v === undefined) return "—";
    if (v === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log10(v) / 3);
    const unit = units[Math.min(i, units.length - 1)];
    const scaled = v / Math.pow(1000, Math.min(i, units.length - 1));
    return `${scaled.toFixed(2)} ${unit}`;
}

// ── Table ────────────────────────────────────────────────────────
const { q, data, loading, error, refresh } = useTable<AdminBackupRow>(
    (q) =>
        opsApi.backups({
            limit: q.limit,
            offset: q.offset,
        }),
    {},
);

const rows = computed(() => data.value?.rows ?? []);
const total = computed(() => data.value?.total ?? 0);

const columns: DataTableColumn<AdminBackupRow>[] = [
    {
        title: "Kind",
        key: "kind",
        width: 120,
        render: (row) =>
            h(
                NTag,
                {
                    type: row.kind === "full" ? "primary" : "default",
                    size: "small",
                },
                { default: () => row.kind },
            ),
    },
    {
        title: "Status",
        key: "status",
        width: 120,
        render: (row) =>
            h(
                NTag,
                { type: STATUS_COLORS[row.status] ?? "default", size: "small" },
                { default: () => row.status },
            ),
    },
    {
        title: "Size",
        key: "size",
        width: 110,
        render: (row) => fmtBytes(row.size),
    },
    {
        title: "Started",
        key: "started_at",
        width: 160,
        render: (row) => fmtDate(row.started_at),
    },
    {
        title: "Finished",
        key: "finished_at",
        width: 160,
        render: (row) => fmtDate(row.finished_at),
    },
    {
        title: "",
        key: "actions",
        width: 110,
        render: (row) => {
            if (row.status !== "completed" || !row.file_path) return null;
            return h(
                NButton,
                {
                    size: "tiny",
                    type: "primary",
                    secondary: true,
                    onClick: (e: MouseEvent) => {
                        e.stopPropagation();
                        handleDownload(row);
                    },
                },
                { default: () => "Download" },
            );
        },
    },
];

// ── Drawer ───────────────────────────────────────────────────────
const drawerOpen = ref(false);
const selectedBackup = ref<AdminBackupRow | null>(null);

function openDrawer(backup: AdminBackupRow) {
    selectedBackup.value = backup;
    drawerOpen.value = true;
}

function closeDrawer() {
    drawerOpen.value = false;
    selectedBackup.value = null;
}

// ── Actions ──────────────────────────────────────────────────────
async function handleStart(kind: "full" | "schema-only") {
    const label = kind === "full" ? "Full backup" : "Schema-only backup";
    const ok = await confirm(
        `Start ${label.toLowerCase()}?`,
        "The backup will run in the background. You can monitor its status in the list.",
    );
    if (!ok) return;
    try {
        await opsApi.startBackup(kind);
        toast.success(`${label} started.`);
        await refresh();
    } catch (e: unknown) {
        toast.error(
            (e as { message?: string }).message ?? "Start backup failed",
        );
    }
}

async function handleDownload(backup: AdminBackupRow) {
    try {
        const resp = await opsApi.downloadUrl(backup.id);
        window.open(resp.download_url, "_blank");
    } catch (e: unknown) {
        toast.error((e as { message?: string }).message ?? "Download failed");
    }
}

// ── Live polling while any backup is running ─────────────────────
const POLL_INTERVAL_MS = 3000;
const hasRunning = computed(() =>
    rows.value.some((r) => r.status === "running"),
);

let pollTimer: ReturnType<typeof setInterval> | null = null;

async function pollOnce() {
    try {
        data.value = await opsApi.backups({ limit: q.limit, offset: q.offset });
    } catch {
        // Swallow polling errors — the next user-initiated refresh surfaces them.
    }
}

watch(
    hasRunning,
    (running) => {
        if (running && pollTimer === null) {
            pollTimer = setInterval(() => {
                void pollOnce();
            }, POLL_INTERVAL_MS);
        } else if (!running && pollTimer !== null) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    },
    { immediate: true },
);

// Keep an open drawer in sync with refreshed list rows.
watch(rows, (next) => {
    if (!selectedBackup.value) return;
    const fresh = next.find((r) => r.id === selectedBackup.value!.id);
    if (fresh) selectedBackup.value = fresh;
});

onUnmounted(() => {
    if (pollTimer !== null) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
});
</script>

<template>
    <NCard title="Backups" size="small">
        <!-- Toolbar -->
        <NSpace style="margin-bottom: 16px">
            <NButton type="primary" size="small" @click="handleStart('full')">
                Start Full Backup
            </NButton>
            <NButton size="small" @click="handleStart('schema-only')">
                Start Schema-only Backup
            </NButton>
        </NSpace>

        <!-- Table area -->
        <ResourceTable
            :q="q"
            :rows="rows"
            :total="total"
            :loading="loading"
            :error="error"
            :columns="columns"
            @refresh="refresh"
        >
            <template #default>
                <NDataTable
                    :columns="columns"
                    :data="rows"
                    :bordered="false"
                    :row-props="
                        (row: AdminBackupRow) => ({
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
            :width="520"
            placement="right"
            :mask-closable="true"
            @update:show="
                (v: boolean) => {
                    if (!v) closeDrawer();
                }
            "
        >
            <NDrawerContent title="Backup detail" closable @close="closeDrawer">
                <template v-if="selectedBackup">
                    <!-- Actions -->
                    <NSpace style="margin-bottom: 20px">
                        <NButton
                            v-if="
                                selectedBackup.status === 'completed' &&
                                selectedBackup.file_path
                            "
                            type="primary"
                            size="small"
                            @click="handleDownload(selectedBackup)"
                        >
                            Download
                        </NButton>
                    </NSpace>

                    <!-- Backup record -->
                    <NDescriptions
                        bordered
                        label-placement="top"
                        :column="1"
                        size="small"
                    >
                        <NDescriptionsItem label="id">
                            <NText code>{{ selectedBackup.id }}</NText>
                        </NDescriptionsItem>
                        <NDescriptionsItem label="kind">
                            <NTag
                                :type="
                                    selectedBackup.kind === 'full'
                                        ? 'primary'
                                        : 'default'
                                "
                                size="small"
                            >
                                {{ selectedBackup.kind }}
                            </NTag>
                        </NDescriptionsItem>
                        <NDescriptionsItem label="status">
                            <NTag
                                :type="
                                    STATUS_COLORS[selectedBackup.status] ??
                                    'default'
                                "
                                size="small"
                            >
                                {{ selectedBackup.status }}
                            </NTag>
                        </NDescriptionsItem>
                        <NDescriptionsItem label="size">
                            {{ fmtBytes(selectedBackup.size) }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="started_at">
                            {{ fmtDate(selectedBackup.started_at) }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="finished_at">
                            {{ fmtDate(selectedBackup.finished_at) }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="created_at">
                            {{ fmtDate(selectedBackup.created_at) }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="file_path">
                            {{ selectedBackup.file_path ?? "—" }}
                        </NDescriptionsItem>
                    </NDescriptions>

                    <template v-if="selectedBackup.error_message">
                        <NDivider />
                        <NText
                            strong
                            style="display: block; margin-bottom: 8px"
                        >
                            Error
                        </NText>
                        <NText
                            type="error"
                            style="white-space: pre-wrap; font-size: 13px"
                        >
                            {{ selectedBackup.error_message }}
                        </NText>
                    </template>
                </template>

                <template v-else>
                    <NText depth="3">Select a backup row to see details.</NText>
                </template>
            </NDrawerContent>
        </NDrawer>
    </NCard>
</template>
