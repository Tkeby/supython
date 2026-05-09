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
    NList,
    NListItem,
    NPagination,
    NSpace,
    NSpin,
    NTag,
    NText,
    NThing,
} from "naive-ui";
import type { DataTableColumn } from "naive-ui";
import ResourceTable from "@/components/data/ResourceTable.vue";
import JsonField from "@/components/data/JsonField.vue";
import EmptyState from "@/components/feedback/EmptyState.vue";
import type { FilterDef } from "@/components/data/filters/types";
import { useTable } from "@/composables/useTable";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import { authApi } from "@/api/resources";
import type { AdminUser, AdminUserDetail } from "@/api/types";

const toast = useToast();
const confirm = useConfirm();

// ── Table ────────────────────────────────────────────────────────
interface UserFilters {
    confirmed: boolean | null;
    banned: boolean | null;
}

const filterDefs: FilterDef[] = [
    {
        type: "boolean",
        key: "confirmed",
        label: "Confirmed",
        trueLabel: "Confirmed",
        falseLabel: "Unconfirmed",
        anyLabel: "Any",
    },
    {
        type: "boolean",
        key: "banned",
        label: "Banned",
        trueLabel: "Banned",
        falseLabel: "Active",
        anyLabel: "Any",
    },
];

const { q, data, loading, error, refresh } = useTable<AdminUser, UserFilters>(
    (q) =>
        authApi.users({
            search: q.search || undefined,
            confirmed: q.filters.confirmed,
            banned: q.filters.banned,
            limit: q.limit,
            offset: q.offset,
        }),
    { confirmed: null, banned: null },
);

const rows = computed(() => data.value?.rows ?? []);
const total = computed(() => data.value?.total ?? 0);

const columns: DataTableColumn<AdminUser>[] = [
    { title: "Email", key: "email" },
    {
        title: "Created",
        key: "created_at",
        width: 120,
        render: (row) => new Date(row.created_at).toLocaleDateString(),
    },
    {
        title: "Last Sign-in",
        key: "last_sign_in_at",
        width: 130,
        render: (row) =>
            row.last_sign_in_at
                ? new Date(row.last_sign_in_at).toLocaleDateString()
                : "—",
    },
    {
        title: "Banned",
        key: "banned_until",
        width: 110,
        render: (row) => {
            if (!row.banned_until) return "No";
            const until = new Date(row.banned_until);
            if (until <= new Date()) return "No";
            return h(
                NTag,
                { type: "error", size: "small" },
                { default: () => `Until ${until.toLocaleDateString()}` },
            );
        },
    },
    {
        title: "Confirmed",
        key: "email_confirmed_at",
        width: 100,
        render: (row) =>
            row.email_confirmed_at
                ? h(
                      NTag,
                      { type: "success", size: "small" },
                      { default: () => "Yes" },
                  )
                : h(
                      NTag,
                      { type: "default", size: "small" },
                      { default: () => "No" },
                  ),
    },
];

// ── Drawer ───────────────────────────────────────────────────────
const drawerOpen = ref(false);
const selectedUserId = ref<string | null>(null);
const drawerData = ref<AdminUserDetail | null>(null);
const drawerLoading = ref(false);
const drawerError = ref<string | null>(null);

function openDrawer(user: AdminUser) {
    selectedUserId.value = user.id;
    drawerOpen.value = true;
    drawerData.value = null;
    drawerError.value = null;
    fetchDrawerDetail(user.id);
}

function closeDrawer() {
    drawerOpen.value = false;
    selectedUserId.value = null;
    drawerData.value = null;
    drawerError.value = null;
}

async function fetchDrawerDetail(userId: string) {
    drawerLoading.value = true;
    drawerError.value = null;
    try {
        drawerData.value = await authApi.getUser(userId);
    } catch (e: unknown) {
        drawerError.value =
            (e as { message?: string }).message ?? "Failed to load user detail";
    } finally {
        drawerLoading.value = false;
    }
}

// ── Action helpers ───────────────────────────────────────────────
const detail = computed(() => drawerData.value);

const isBanned = computed(() => {
    if (!detail.value?.user.banned_until) return false;
    return new Date(detail.value.user.banned_until) > new Date();
});

async function handleBan() {
    if (!selectedUserId.value || !detail.value) return;
    const email = detail.value.user.email;
    const ok = await confirm(
        `Ban user "${email}" for 24h?`,
        "They cannot sign in until unbanned.",
    );
    if (!ok) return;
    try {
        await authApi.banUser(selectedUserId.value);
        toast.success("Banned.");
        await fetchDrawerDetail(selectedUserId.value);
        await refresh();
    } catch (e: unknown) {
        toast.error((e as { message?: string }).message ?? "Ban failed");
    }
}

async function handleUnban() {
    if (!selectedUserId.value || !detail.value) return;
    const email = detail.value.user.email;
    const ok = await confirm(
        `Unban user "${email}"?`,
        "They will be able to sign in again.",
    );
    if (!ok) return;
    try {
        await authApi.unbanUser(selectedUserId.value);
        toast.success("Unbanned.");
        await fetchDrawerDetail(selectedUserId.value);
        await refresh();
    } catch (e: unknown) {
        toast.error((e as { message?: string }).message ?? "Unban failed");
    }
}

async function handleForceLogout() {
    if (!selectedUserId.value || !detail.value) return;
    const email = detail.value.user.email;
    const ok = await confirm(
        `Force logout user "${email}"?`,
        "All their refresh tokens will be revoked immediately.",
    );
    if (!ok) return;
    try {
        const result = await authApi.forceLogout(selectedUserId.value);
        toast.success(`Force logout — ${result.revoked} token(s) revoked.`);
        await fetchDrawerDetail(selectedUserId.value);
        await refresh();
    } catch (e: unknown) {
        toast.error(
            (e as { message?: string }).message ?? "Force logout failed",
        );
    }
}
</script>

<template>
    <NCard title="Users" size="small">
        <!-- Table area -->
        <ResourceTable
            :q="q"
            :rows="rows"
            :total="total"
            :loading="loading"
            :error="error"
            :columns="columns"
            :filters="filterDefs"
            search-placeholder="Search by email…"
            @refresh="refresh"
        >
            <template #default>
                <NDataTable
                    :columns="columns"
                    :data="rows"
                    :bordered="false"
                    :row-props="
                        (row: AdminUser) => ({
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
            <NDrawerContent title="User detail" closable @close="closeDrawer">
                <template v-if="drawerLoading">
                    <NSpace vertical align="center" style="padding: 48px 0">
                        <NSpin />
                        <NText depth="3">Loading…</NText>
                    </NSpace>
                </template>

                <template v-else-if="drawerError">
                    <NSpace vertical align="center" style="padding: 32px 0">
                        <NText type="error">{{ drawerError }}</NText>
                        <NButton
                            size="small"
                            @click="
                                selectedUserId &&
                                fetchDrawerDetail(selectedUserId)
                            "
                            >Retry</NButton
                        >
                    </NSpace>
                </template>

                <template v-else-if="detail">
                    <!-- Actions -->
                    <NSpace style="margin-bottom: 20px">
                        <NButton
                            v-if="!isBanned"
                            type="warning"
                            size="small"
                            @click="handleBan"
                        >
                            Ban 24h
                        </NButton>
                        <NButton
                            v-else
                            type="success"
                            size="small"
                            @click="handleUnban"
                        >
                            Unban
                        </NButton>
                        <NButton
                            type="error"
                            size="small"
                            secondary
                            @click="handleForceLogout"
                        >
                            Force Logout
                        </NButton>
                    </NSpace>

                    <!-- User record -->
                    <NDescriptions
                        bordered
                        label-placement="top"
                        :column="1"
                        size="small"
                    >
                        <NDescriptionsItem label="id">
                            <NText code>{{ detail.user.id }}</NText>
                        </NDescriptionsItem>
                        <NDescriptionsItem label="email">
                            {{ detail.user.email }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="created_at">
                            {{
                                new Date(
                                    detail.user.created_at,
                                ).toLocaleString()
                            }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="last_sign_in_at">
                            {{
                                detail.user.last_sign_in_at
                                    ? new Date(
                                          detail.user.last_sign_in_at,
                                      ).toLocaleString()
                                    : "—"
                            }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="email_confirmed_at">
                            {{
                                detail.user.email_confirmed_at
                                    ? new Date(
                                          detail.user.email_confirmed_at,
                                      ).toLocaleString()
                                    : "—"
                            }}
                        </NDescriptionsItem>
                        <NDescriptionsItem label="banned_until">
                            {{
                                isBanned
                                    ? new Date(
                                          detail.user.banned_until!,
                                      ).toLocaleString()
                                    : "Not banned"
                            }}
                        </NDescriptionsItem>
                    </NDescriptions>

                    <NDivider />

                    <!-- Identities -->
                    <NText strong style="display: block; margin-bottom: 8px">
                        Identities ({{ detail.identities.length }})
                    </NText>
                    <NDataTable
                        v-if="detail.identities.length"
                        :columns="[
                            { title: 'Provider', key: 'provider' },
                            {
                                title: 'Provider User ID',
                                key: 'provider_user_id',
                            },
                            {
                                title: 'Data',
                                key: 'identity_data',
                                render: (row: any) =>
                                    h(JsonField, { value: row.identity_data }),
                            },
                        ]"
                        :data="detail.identities"
                        :bordered="false"
                        size="small"
                        style="margin-bottom: 16px"
                    />
                    <EmptyState v-else description="No linked identities." />

                    <NDivider />

                    <!-- Recent audit -->
                    <NText strong style="display: block; margin-bottom: 8px">
                        Recent audit events ({{ detail.recent_audit.length }})
                    </NText>
                    <NList v-if="detail.recent_audit.length" hoverable>
                        <NListItem
                            v-for="evt in detail.recent_audit"
                            :key="evt.id"
                        >
                            <NThing
                                :title="evt.event"
                                :description="
                                    new Date(evt.created_at).toLocaleString()
                                "
                            >
                                <template v-if="evt.ip">
                                    <NText depth="3" style="font-size: 12px"
                                        >IP: {{ evt.ip }}</NText
                                    >
                                </template>
                            </NThing>
                        </NListItem>
                    </NList>
                    <EmptyState v-else description="No recent audit events." />
                </template>

                <template v-else>
                    <NText depth="3">Select a user row to see details.</NText>
                </template>
            </NDrawerContent>
        </NDrawer>
    </NCard>
</template>
