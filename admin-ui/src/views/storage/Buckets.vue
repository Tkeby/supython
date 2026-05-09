<script setup lang="ts">
import { useRouter } from "vue-router";
import { NCard, NGrid, NGridItem, NSpin, NTag, NText } from "naive-ui";
import { useResource } from "@/composables/useResource";
import { storageApi } from "@/api/resources";
import type { AdminBucket } from "@/api/types";
import EmptyState from "@/components/feedback/EmptyState.vue";
import ErrorState from "@/components/feedback/ErrorState.vue";

const router = useRouter();

const {
    data: buckets,
    loading,
    error,
    refresh,
} = useResource(() => storageApi.buckets());

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

function openBucket(bucket: AdminBucket) {
    router.push(`/storage/${encodeURIComponent(bucket.name)}`);
}

type TagType = "default" | "info" | "warning" | "error" | "success" | "primary";

function publicColor(public_: boolean, bucket: AdminBucket): TagType {
    if (public_) return "success";
    return bucket.object_count > 0 ? "warning" : "default";
}
</script>

<template>
    <div>
        <div
            style="
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 16px;
            "
        >
            <h1 style="margin: 0; font-size: 20px; font-weight: 600">
                Storage Buckets
            </h1>
        </div>

        <ErrorState :error="error" :retry="refresh" />

        <NSpin :show="loading">
            <template v-if="buckets && buckets.length">
                <NGrid
                    cols="1 s:2 m:3 l:4"
                    responsive="screen"
                    :x-gap="16"
                    :y-gap="16"
                >
                    <NGridItem v-for="bucket in buckets" :key="bucket.id">
                        <NCard
                            size="small"
                            hoverable
                            :segmented="{ content: true }"
                            @click="openBucket(bucket)"
                        >
                            <template #header>
                                <div
                                    style="
                                        display: flex;
                                        align-items: center;
                                        gap: 8px;
                                    "
                                >
                                    <NTag
                                        :type="
                                            publicColor(bucket.public, bucket)
                                        "
                                        size="small"
                                        :bordered="false"
                                    >
                                        {{
                                            bucket.public ? "Public" : "Private"
                                        }}
                                    </NTag>
                                    <NText
                                        strong
                                        style="
                                            font-size: 14px;
                                            flex: 1;
                                            min-width: 0;
                                            overflow: hidden;
                                            text-overflow: ellipsis;
                                            white-space: nowrap;
                                        "
                                    >
                                        {{ bucket.name }}
                                    </NText>
                                </div>
                            </template>

                            <div
                                style="
                                    display: grid;
                                    grid-template-columns: 1fr 1fr;
                                    gap: 12px;
                                "
                            >
                                <div>
                                    <NText
                                        depth="3"
                                        style="
                                            font-size: 11px;
                                            display: block;
                                            margin-bottom: 2px;
                                        "
                                    >
                                        Objects
                                    </NText>
                                    <NText strong style="font-size: 20px">
                                        {{
                                            bucket.object_count.toLocaleString()
                                        }}
                                    </NText>
                                </div>
                                <div>
                                    <NText
                                        depth="3"
                                        style="
                                            font-size: 11px;
                                            display: block;
                                            margin-bottom: 2px;
                                        "
                                    >
                                        Total Size
                                    </NText>
                                    <NText strong style="font-size: 16px">
                                        {{ formatBytes(bucket.total_size) }}
                                    </NText>
                                </div>
                            </div>

                            <div style="margin-top: 12px">
                                <NText
                                    depth="3"
                                    style="
                                        font-size: 11px;
                                        display: block;
                                        margin-bottom: 2px;
                                    "
                                >
                                    Owner
                                </NText>
                                <NText code style="font-size: 12px">
                                    {{
                                        bucket.owner
                                            ? bucket.owner.slice(0, 8) + "…"
                                            : "(none)"
                                    }}
                                </NText>
                            </div>

                            <div style="margin-top: 8px">
                                <NText depth="3" style="font-size: 11px">
                                    Created
                                    {{
                                        new Date(
                                            bucket.created_at,
                                        ).toLocaleDateString()
                                    }}
                                </NText>
                            </div>
                        </NCard>
                    </NGridItem>
                </NGrid>
            </template>

            <template v-else-if="buckets && !buckets.length">
                <EmptyState description="No storage buckets found." />
            </template>
        </NSpin>
    </div>
</template>
