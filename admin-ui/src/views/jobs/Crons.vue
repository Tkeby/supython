<script setup lang="ts">
import { computed, h } from "vue";
import { NAlert, NButton, NCard, NDataTable, NSpin, NTag } from "naive-ui";
import type { DataTableColumn } from "naive-ui";
import EmptyState from "@/components/feedback/EmptyState.vue";
import ErrorState from "@/components/feedback/ErrorState.vue";
import { useResource } from "@/composables/useResource";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import { jobsApi } from "@/api/resources";
import type { AdminCronRow } from "@/api/types";

const toast = useToast();
const confirm = useConfirm();

// ── Health ───────────────────────────────────────────────────────
const {
    data: health,
    error: healthError,
    loading: healthLoading,
    refresh: refreshHealth,
} = useResource(() => jobsApi.cronHealth());

const healthBanner = computed(() => {
    if (!health.value) return null;
    if (health.value.installed) {
        return {
            type: "success" as const,
            message: `pg_cron v${health.value.extension_version ?? "?"} — ${health.value.active_jobs} active schedule(s)`,
        };
    }
    return {
        type: "warning" as const,
        message:
            "pg_cron is not installed. Cron jobs will not fire automatically.",
    };
});

// ── Cron table ───────────────────────────────────────────────────
const {
    data: crons,
    error: cronsError,
    loading: cronsLoading,
    refresh: refreshCrons,
} = useResource(() => jobsApi.crons());

function fmtDate(v: string | null): string {
    return v ? new Date(v).toLocaleString() : "—";
}

const columns: DataTableColumn<AdminCronRow>[] = [
    { title: "Name", key: "name", ellipsis: { tooltip: true } },
    { title: "Schedule", key: "cron_expr", width: 120 },
    { title: "Job", key: "job_name", width: 140 },
    {
        title: "Enabled",
        key: "enabled",
        width: 100,
        render: (row) =>
            h(
                NTag,
                { type: row.enabled ? "success" : "default", size: "small" },
                { default: () => (row.enabled ? "Yes" : "No") },
            ),
    },
    {
        title: "pg_cron Active",
        key: "pg_cron_active",
        width: 130,
        render: (row) => {
            if (row.pg_cron_active === null) return "—";
            return h(
                NTag,
                {
                    type: row.pg_cron_active ? "success" : "warning",
                    size: "small",
                },
                { default: () => (row.pg_cron_active ? "Yes" : "No") },
            );
        },
    },
    {
        title: "Last Fire",
        key: "last_fire_at",
        width: 160,
        render: (row) => fmtDate(row.last_fire_at),
    },
    {
        title: "Created",
        key: "created_at",
        width: 160,
        render: (row) => fmtDate(row.created_at),
    },
    {
        title: "",
        key: "actions",
        width: 100,
        render: (row) =>
            h(
                NButton,
                {
                    size: "tiny",
                    type: "info",
                    onClick: () => handleRunNow(row),
                },
                { default: () => "Run now" },
            ),
    },
];

// ── Actions ──────────────────────────────────────────────────────
async function handleRunNow(cron: AdminCronRow) {
    const ok = await confirm(
        `Run cron "${cron.name}" now?`,
        `This will enqueue a ${cron.job_name} job immediately.`,
    );
    if (!ok) return;
    try {
        await jobsApi.runCronNow(cron.name);
        toast.success(`Enqueued ${cron.job_name}`);
        await refreshCrons();
    } catch (e: unknown) {
        toast.error((e as { message?: string }).message ?? "Run-now failed");
    }
}
</script>

<template>
    <NCard title="Cron Schedules" size="small">
        <!-- Health banner -->
        <NSpin :show="healthLoading" size="small" style="margin-bottom: 16px">
            <ErrorState :error="healthError" :retry="refreshHealth" />
            <NAlert
                v-if="healthBanner"
                :type="healthBanner.type"
                :show-icon="true"
                style="margin-bottom: 16px"
            >
                {{ healthBanner.message }}
            </NAlert>
        </NSpin>

        <!-- Cron table -->
        <NSpin :show="cronsLoading">
            <ErrorState :error="cronsError" :retry="refreshCrons" />
            <NDataTable
                v-if="crons && crons.length > 0"
                :columns="columns"
                :data="crons"
                :bordered="false"
            />
            <EmptyState
                v-else-if="crons && crons.length === 0"
                description="No cron schedules defined."
            />
        </NSpin>
    </NCard>
</template>
