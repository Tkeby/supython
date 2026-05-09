<script setup lang="ts">
import { computed, h, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
    NButton,
    NCard,
    NDataTable,
    NDivider,
    NInput,
    NModal,
    NSelect,
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
import { storageApi } from "@/api/resources";
import type {
    AdminObject,
    AdminSignedUrlResponse,
    SignRole,
} from "@/api/types";

const route = useRoute();
const router = useRouter();
const toast = useToast();
const confirm = useConfirm();

const bucket = computed(() => String(route.params.bucket));

// ── Table ────────────────────────────────────────────────────────
const prefixFilter = ref("");

interface ObjectFilters {
    _dummy: null;
}

const { q, data, loading, error, refresh } = useTable<
    AdminObject,
    ObjectFilters
>(
    (q) =>
        storageApi.objects(bucket.value, {
            prefix: prefixFilter.value || undefined,
            limit: q.limit,
            offset: q.offset,
        }),
    { _dummy: null },
);

const rows = computed(() => data.value?.rows ?? []);
const total = computed(() => data.value?.total ?? 0);

function formatBytes(bytes: number): string {
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.min(
        Math.floor(Math.log(bytes) / Math.log(1024)),
        units.length - 1,
    );
    const v = bytes / Math.pow(1024, i);
    return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

// ── Quick Download ───────────────────────────────────────────────
async function handleDownload(obj: AdminObject) {
    try {
        const res = await storageApi.sign(obj.id, 300); // 5 min
        window.open(res.signed_url, "_blank");
    } catch (e: unknown) {
        toast.error((e as { message?: string }).message ?? "Download failed");
    }
}

// ── Sign Modal ───────────────────────────────────────────────────
const signModalOpen = ref(false);
const signModalLoading = ref(false);
const signTarget = ref<AdminObject | null>(null);
const signResult = ref<AdminSignedUrlResponse | null>(null);

const signTTL = ref(3600); // default 1h
const signRole = ref<SignRole>("service_role");
const signImpersonateSub = ref("");

const ttlOptions = [
    { label: "5 minutes", value: 300 },
    { label: "1 hour", value: 3600 },
    { label: "6 hours", value: 21600 },
    { label: "24 hours", value: 86400 },
    { label: "7 days", value: 604800 },
];

const roleOptions: { label: string; value: SignRole }[] = [
    { label: "service_role", value: "service_role" },
    { label: "authenticated", value: "authenticated" },
    { label: "anon", value: "anon" },
];

function openSignModal(obj: AdminObject) {
    signTarget.value = obj;
    signResult.value = null;
    signTTL.value = 3600;
    signRole.value = "service_role";
    signImpersonateSub.value = "";
    signModalOpen.value = true;
}

function closeSignModal() {
    signModalOpen.value = false;
    signTarget.value = null;
    signResult.value = null;
}

async function handleSign() {
    if (!signTarget.value) return;
    signModalLoading.value = true;
    signResult.value = null;
    try {
        const res = await storageApi.sign(
            signTarget.value.id,
            signTTL.value,
            signRole.value,
            signImpersonateSub.value || undefined,
        );
        signResult.value = res;
        toast.success("Signed URL generated.");
    } catch (e: unknown) {
        toast.error((e as { message?: string }).message ?? "Sign failed");
    } finally {
        signModalLoading.value = false;
    }
}

function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text).then(
        () => toast.success("Copied to clipboard."),
        () => toast.error("Failed to copy."),
    );
}

function openSignedUrl(url: string) {
    window.open(url, "_blank");
}

// ── Delete ───────────────────────────────────────────────────────
async function handleDelete(obj: AdminObject) {
    const ok = await confirm(
        "Delete object?",
        `Delete "${obj.name}" from bucket "${bucket.value}"? This action cannot be undone.`,
    );
    if (!ok) return;
    try {
        await storageApi.deleteObject(obj.id);
        toast.success(`Object "${obj.name}" deleted.`);
        await refresh();
    } catch (e: unknown) {
        toast.error((e as { message?: string }).message ?? "Delete failed");
    }
}

// ── Columns ──────────────────────────────────────────────────────
const columns: DataTableColumn<AdminObject>[] = [
    {
        title: "Name",
        key: "name",
        ellipsis: { tooltip: true },
    },
    {
        title: "Size",
        key: "size",
        width: 100,
        render: (row) => formatBytes(row.size),
    },
    {
        title: "Type",
        key: "mime_type",
        width: 140,
        ellipsis: { tooltip: true },
        render: (row) =>
            row.mime_type
                ? h(
                      NTag,
                      { size: "small", bordered: false },
                      { default: () => row.mime_type },
                  )
                : h(NText, { depth: 3 }, { default: () => "—" }),
    },
    {
        title: "Updated",
        key: "updated_at",
        width: 140,
        render: (row) => new Date(row.updated_at).toLocaleDateString(),
    },
    {
        title: "Actions",
        key: "actions",
        width: 220,
        render: (row) =>
            h(NSpace, { size: "small" }, () => [
                h(
                    NButton,
                    {
                        size: "tiny",
                        secondary: true,
                        onClick: () => handleDownload(row),
                    },
                    { default: () => "Download" },
                ),
                h(
                    NButton,
                    {
                        size: "tiny",
                        type: "info",
                        onClick: () => openSignModal(row),
                    },
                    { default: () => "Sign" },
                ),
                h(
                    NButton,
                    {
                        size: "tiny",
                        type: "error",
                        secondary: true,
                        onClick: () => handleDelete(row),
                    },
                    { default: () => "Delete" },
                ),
            ]),
    },
];
</script>

<template>
    <div>
        <!-- Header -->
        <div
            style="
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 16px;
            "
        >
            <NButton size="small" secondary @click="router.push('/storage')">
                ← Buckets
            </NButton>
            <h1 style="margin: 0; font-size: 20px; font-weight: 600">
                <NText code>{{ bucket }}</NText>
            </h1>
        </div>

        <!-- Prefix filter -->
        <div style="margin-bottom: 16px">
            <div
                style="
                    margin-bottom: 4px;
                    font-size: 12px;
                    color: rgba(255, 255, 255, 0.55);
                "
            >
                Prefix filter (path-aware)
            </div>
            <NSpace align="end">
                <NInput
                    v-model:value="prefixFilter"
                    placeholder="e.g. images/2024/ or leave empty for all"
                    clearable
                    style="width: 420px"
                    @keyup.enter="refresh()"
                    @clear="refresh()"
                />
                <NButton size="small" secondary @click="refresh()"
                    >Apply</NButton
                >
            </NSpace>
        </div>

        <!-- Table -->
        <NCard size="small">
            <ResourceTable
                :q="q"
                :rows="rows"
                :total="total"
                :loading="loading"
                :error="error"
                :columns="columns"
                search-placeholder="Filter rows…"
                @refresh="refresh"
            >
                <template #default>
                    <NDataTable
                        :columns="columns"
                        :data="rows"
                        :bordered="false"
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
        </NCard>

        <!-- Sign Modal -->
        <NModal
            :show="signModalOpen"
            :mask-closable="true"
            @update:show="
                (v: boolean) => {
                    if (!v) closeSignModal();
                }
            "
        >
            <NCard
                style="width: 520px; max-width: 90vw"
                title="Generate Signed URL"
                size="small"
                role="dialog"
                aria-modal="true"
            >
                <template #header-extra>
                    <NButton size="tiny" quaternary @click="closeSignModal"
                        >✕</NButton
                    >
                </template>

                <template v-if="signTarget">
                    <!-- Object info -->
                    <NText
                        depth="3"
                        style="
                            font-size: 12px;
                            display: block;
                            margin-bottom: 4px;
                        "
                    >
                        Object
                    </NText>
                    <NText code style="font-size: 13px; word-break: break-all">
                        {{ signTarget.name }}
                    </NText>
                    <NText
                        depth="3"
                        style="font-size: 12px; display: block; margin-top: 2px"
                    >
                        {{ formatBytes(signTarget.size) }} ·
                        {{ signTarget.mime_type ?? "unknown type" }}
                    </NText>

                    <NDivider />

                    <!-- TTL -->
                    <div style="margin-bottom: 16px">
                        <NText
                            strong
                            style="
                                display: block;
                                margin-bottom: 6px;
                                font-size: 13px;
                            "
                        >
                            Expires In
                        </NText>
                        <NSelect
                            v-model:value="signTTL"
                            :options="ttlOptions"
                            style="width: 100%"
                        />
                    </div>

                    <!-- Role -->
                    <div style="margin-bottom: 16px">
                        <NText
                            strong
                            style="
                                display: block;
                                margin-bottom: 6px;
                                font-size: 13px;
                            "
                        >
                            Sign Under Role
                        </NText>
                        <NSelect
                            v-model:value="signRole"
                            :options="roleOptions"
                            style="width: 100%"
                        />
                    </div>

                    <!-- Impersonate sub -->
                    <div style="margin-bottom: 16px">
                        <NText
                            strong
                            style="
                                display: block;
                                margin-bottom: 6px;
                                font-size: 13px;
                            "
                        >
                            Impersonate User ID (optional)
                        </NText>
                        <NInput
                            v-model:value="signImpersonateSub"
                            placeholder="UUID of the user to impersonate"
                            clearable
                        />
                    </div>

                    <!-- Generate button -->
                    <NButton
                        type="primary"
                        :loading="signModalLoading"
                        block
                        @click="handleSign"
                    >
                        Generate Signed URL
                    </NButton>

                    <!-- Result -->
                    <template v-if="signResult">
                        <NDivider />

                        <NText
                            strong
                            style="
                                display: block;
                                margin-bottom: 8px;
                                font-size: 13px;
                            "
                        >
                            Result
                        </NText>

                        <!-- Role disclosure -->
                        <div
                            style="
                                padding: 8px 12px;
                                border-radius: 4px;
                                background: rgba(16, 185, 129, 0.1);
                                border: 1px solid rgba(16, 185, 129, 0.25);
                                margin-bottom: 12px;
                            "
                        >
                            <NText
                                depth="3"
                                style="font-size: 11px; display: block"
                            >
                                Signed under role
                            </NText>
                            <NTag
                                type="success"
                                size="small"
                                style="margin-top: 4px"
                            >
                                {{ signResult.signed_under_role }}
                            </NTag>
                        </div>

                        <!-- Signed URL -->
                        <div style="margin-bottom: 8px">
                            <NText
                                depth="3"
                                style="
                                    font-size: 11px;
                                    display: block;
                                    margin-bottom: 4px;
                                "
                            >
                                Signed URL (expires
                                {{
                                    new Date(
                                        signResult.expires_at,
                                    ).toLocaleString()
                                }})
                            </NText>
                            <textarea
                                :value="signResult.signed_url"
                                readonly
                                rows="3"
                                style="
                                    width: 100%;
                                    padding: 8px 10px;
                                    border-radius: 4px;
                                    border: 1px solid rgba(255, 255, 255, 0.12);
                                    background: rgba(255, 255, 255, 0.05);
                                    color: inherit;
                                    font-family: monospace;
                                    font-size: 12px;
                                    resize: vertical;
                                    outline: none;
                                    box-sizing: border-box;
                                    word-break: break-all;
                                "
                            />
                        </div>

                        <NSpace>
                            <NButton
                                size="small"
                                secondary
                                @click="copyToClipboard(signResult.signed_url)"
                            >
                                Copy URL
                            </NButton>
                            <NButton
                                size="small"
                                @click="openSignedUrl(signResult.signed_url)"
                            >
                                Open
                            </NButton>
                        </NSpace>
                    </template>
                </template>
            </NCard>
        </NModal>
    </div>
</template>
