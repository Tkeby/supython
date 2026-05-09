<script setup lang="ts">
import { ref, shallowRef } from "vue";
import { NButton, NCard, NInput, NSpace, NTabPane, NTabs } from "naive-ui";
import LiveTail from "@/components/feedback/LiveTail.vue";
import EmptyState from "@/components/feedback/EmptyState.vue";
import { useLiveTail } from "@/composables/useLiveTail";
import Tables from "./Tables.vue";
import type { RealtimeFrame } from "@/api/types";

const activeTab = ref("inspector");

// ── Topic input ────────────────────────────────────────────────
const topicInput = ref("realtime:public");
const activeTopic = ref<string | null>(null);

// ── Live tail ──────────────────────────────────────────────────
const tail = shallowRef<ReturnType<typeof useLiveTail<RealtimeFrame>> | null>(
    null,
);

function parseFrame(eventName: string, rawData: string): RealtimeFrame {
    const parsed = JSON.parse(rawData) as {
        topic?: string;
        payload?: Record<string, unknown>;
    };
    return {
        event: eventName,
        topic: parsed.topic ?? "",
        payload: parsed.payload ?? { raw: rawData },
        receivedAt: new Date(),
    };
}

const SSE_EVENTS = [
    "postgres_changes",
    "broadcast",
    "presence",
    "presence_diff",
    "presence_state",
    "connected",
    "heartbeat",
    "error",
];

function connect() {
    const topic = topicInput.value.trim();
    if (!topic) return;

    // Tear down existing connection
    disconnect();

    activeTopic.value = topic;
    tail.value = useLiveTail<RealtimeFrame>(
        `/realtime/inspect?topic=${encodeURIComponent(topic)}`,
        parseFrame,
        SSE_EVENTS,
    );
}

function disconnect() {
    if (tail.value) {
        tail.value.close();
    }
    tail.value = null;
    activeTopic.value = null;
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
                Realtime
            </h1>
        </div>

        <NTabs v-model:value="activeTab" type="line" animated>
            <!-- Inspector tab (Story 10.2) -->
            <NTabPane name="inspector" tab="Inspector">
                <NCard size="small">
                    <NSpace vertical :size="16">
                        <!-- Topic bar -->
                        <NSpace align="center" :size="8">
                            <NInput
                                v-model:value="topicInput"
                                placeholder="e.g. realtime:room-42"
                                style="width: 340px"
                                :disabled="!!tail"
                                @keyup.enter="connect"
                            />
                            <NButton
                                v-if="!tail"
                                type="primary"
                                size="small"
                                @click="connect"
                            >
                                Connect
                            </NButton>
                            <NButton v-else size="small" @click="disconnect">
                                Disconnect
                            </NButton>
                        </NSpace>

                        <!-- Live tail -->
                        <template v-if="tail">
                            <LiveTail
                                :events="tail.events.value"
                                :connected="tail.connected.value"
                                :paused="tail.paused.value"
                                @pause="tail.pause()"
                                @resume="tail.resume()"
                                @clear="tail.clear()"
                            />
                        </template>

                        <EmptyState
                            v-else
                            description="Subscribe to a topic to begin tailing."
                        />
                    </NSpace>
                </NCard>
            </NTabPane>

            <!-- Tables tab (Story 10.1) -->
            <NTabPane name="tables" tab="Enabled Tables">
                <Tables />
            </NTabPane>
        </NTabs>
    </div>
</template>
