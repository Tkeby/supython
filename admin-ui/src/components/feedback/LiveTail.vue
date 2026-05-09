<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { NButton, NSpace, NTag, NText } from "naive-ui";
import JsonField from "@/components/data/JsonField.vue";

interface TailEvent {
    event: string;
    payload: Record<string, unknown>;
    receivedAt: Date;
}

const props = defineProps<{
    events: TailEvent[];
    connected: boolean;
    paused: boolean;
}>();

const emit = defineEmits<{
    (e: "pause"): void;
    (e: "resume"): void;
    (e: "clear"): void;
}>();

const listEl = ref<HTMLElement | null>(null);
const autoScroll = ref(true);

function eventTypeColor(
    event: string,
): "info" | "success" | "warning" | "error" | "default" {
    if (event === "postgres_changes") return "info";
    if (event === "broadcast") return "success";
    if (event === "presence") return "warning";
    if (event === "error") return "error";
    return "default";
}

function formatTime(d: Date): string {
    return d.toLocaleTimeString("en-US", {
        hour12: false,
        fractionalSecondDigits: 3,
    });
}

watch(
    () => props.events.length,
    async () => {
        if (!autoScroll.value) return;
        await nextTick();
        const el = listEl.value;
        if (el) el.scrollTop = el.scrollHeight;
    },
);

function onScroll() {
    const el = listEl.value;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    autoScroll.value = atBottom;
}
</script>

<template>
    <div>
        <!-- Controls -->
        <NSpace align="center" :size="8" style="margin-bottom: 8px">
            <NTag
                :type="connected ? 'success' : 'default'"
                size="small"
                :bordered="false"
            >
                {{ connected ? "Connected" : "Disconnected" }}
            </NTag>
            <NTag v-if="paused" type="warning" size="small" :bordered="false">
                Paused
            </NTag>
            <NText depth="3" style="font-size: 12px">
                {{ events.length.toLocaleString() }} events
            </NText>
            <NButton v-if="!paused" size="tiny" @click="emit('pause')"
                >Pause</NButton
            >
            <NButton v-else size="tiny" type="info" @click="emit('resume')"
                >Resume</NButton
            >
            <NButton size="tiny" @click="emit('clear')">Clear</NButton>
        </NSpace>

        <!-- Event list -->
        <div
            ref="listEl"
            style="
                height: calc(100vh - 380px);
                min-height: 200px;
                overflow-y: auto;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 4px;
                background: rgba(0, 0, 0, 0.15);
            "
            @scroll="onScroll"
        >
            <div
                v-if="events.length === 0"
                style="padding: 40px; text-align: center"
            >
                <NText depth="3" style="font-size: 13px">
                    Waiting for events…
                </NText>
            </div>
            <div
                v-for="(evt, i) in events"
                :key="i"
                style="
                    display: flex;
                    align-items: flex-start;
                    gap: 10px;
                    padding: 6px 12px;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
                    font-family: monospace;
                    font-size: 12px;
                "
            >
                <NText
                    depth="3"
                    style="white-space: nowrap; flex-shrink: 0; min-width: 88px"
                >
                    {{ formatTime(evt.receivedAt) }}
                </NText>
                <NTag
                    :type="eventTypeColor(evt.event)"
                    size="tiny"
                    style="flex-shrink: 0"
                >
                    {{ evt.event }}
                </NTag>
                <div style="min-width: 0; flex: 1">
                    <JsonField :value="evt.payload" />
                </div>
            </div>
        </div>
    </div>
</template>
