<script setup lang="ts">
import { computed, h, onBeforeUnmount, ref, watch } from "vue";
import {
    NButton,
    NCard,
    NInput,
    NScrollbar,
    NSelect,
    NSpace,
    NTag,
    NText,
} from "naive-ui";
import type { SelectOption } from "naive-ui";
import { useConfirm } from "@/composables/useConfirm";
import { useToast } from "@/composables/useToast";
import type { LogEntry } from "@/api/types";

// ── Debounce helper ──────────────────────────────────────────────

function useDebounce(fn: () => void, ms: number) {
    let timer: ReturnType<typeof setTimeout> | null = null;
    return () => {
        if (timer !== null) clearTimeout(timer);
        timer = setTimeout(fn, ms);
    };
}

// ── Constants ────────────────────────────────────────────────────

const LEVEL_OPTIONS: SelectOption[] = [
    { label: "All levels", value: "" },
    { label: "DEBUG", value: "DEBUG" },
    { label: "INFO", value: "INFO" },
    { label: "WARNING", value: "WARNING" },
    { label: "ERROR", value: "ERROR" },
    { label: "CRITICAL", value: "CRITICAL" },
];

const LEVEL_COLORS: Record<string, "default" | "info" | "warning" | "error"> = {
    DEBUG: "default",
    INFO: "info",
    WARNING: "warning",
    ERROR: "error",
    CRITICAL: "error",
};

function fmtTime(ts: string): string {
    try {
        return new Date(ts).toLocaleTimeString();
    } catch {
        return ts;
    }
}

const MAX_ROWS = 5000;

// ── Filters ──────────────────────────────────────────────────────

const level = ref("");
const substring = ref("");
const requestIdFilter = ref("");

function _buildUrl(): string {
    const params = new URLSearchParams();
    if (level.value) params.set("level", level.value);
    if (substring.value) params.set("substring", substring.value);
    if (requestIdFilter.value) params.set("request_id", requestIdFilter.value);
    const qs = params.toString();
    return `/admin/api/v1/ops/logs/tail${qs ? "?" + qs : ""}`;
}

// ── Log store ────────────────────────────────────────────────────

const rows = ref<LogEntry[]>([]);

function appendEntries(entries: LogEntry[]) {
    rows.value.push(...entries);
    // Trim oldest if over capacity
    if (rows.value.length > MAX_ROWS) {
        rows.value = rows.value.slice(rows.value.length - MAX_ROWS);
    }
}

// ── SSE connection ───────────────────────────────────────────────

const paused = ref(false);
const connected = ref(false);
const snapshotReceived = ref(false);
let eventSource: EventSource | null = null;
let pending: LogEntry[] = [];
let connecting = false;

function connect() {
    if (eventSource || connecting) return;
    connecting = true;
    snapshotReceived.value = false;

    eventSource = new EventSource(_buildUrl(), { withCredentials: true });

    eventSource.addEventListener("logs:snapshot", (e: MessageEvent) => {
        try {
            const data: LogEntry[] = JSON.parse(e.data);
            rows.value = data.slice(0, MAX_ROWS);
            snapshotReceived.value = true;
        } catch {
            // silently skip malformed data
        }
    });

    eventSource.addEventListener("logs:append", (e: MessageEvent) => {
        try {
            const entry: LogEntry = JSON.parse(e.data);
            if (paused.value) {
                pending.push(entry);
                if (pending.length > MAX_ROWS) {
                    pending = pending.slice(pending.length - MAX_ROWS);
                }
            } else {
                appendEntries([entry]);
            }
        } catch {
            // silently skip malformed data
        }
    });

    eventSource.onopen = () => {
        connected.value = true;
        connecting = false;
    };

    eventSource.onerror = () => {
        connected.value = false;
        connecting = false;
        // EventSource auto-reconnects after a delay for transient failures.
        // If we deliberately closed it (readyState === CLOSED) we clear the
        // reference in disconnect() so this won't fire for deliberate closes.
    };
}

function disconnect() {
    connecting = false;
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    connected.value = false;
}

function reconnect() {
    disconnect();
    rows.value = [];
    pending = [];
    connect();
}

// Debounced reconnect so rapid typing doesn't thrash the EventSource.
const _debouncedReconnect = useDebounce(reconnect, 300);

watch([level, substring, requestIdFilter], () => {
    _debouncedReconnect();
});

// Auto-connect on mount
connect();

onBeforeUnmount(() => {
    disconnect();
});

// ── Pause / Resume ───────────────────────────────────────────────

function togglePause() {
    paused.value = !paused.value;
    if (!paused.value && pending.length > 0) {
        appendEntries(pending);
        pending = [];
    }
}

// ── Clear ────────────────────────────────────────────────────────

const confirm = useConfirm();
const toast = useToast();

async function handleClear() {
    const ok = await confirm(
        "Clear all log entries?",
        "This cannot be undone.",
    );
    if (!ok) return;
    rows.value = [];
    pending = [];
}

// ── Download ─────────────────────────────────────────────────────

function handleDownload() {
    const json = JSON.stringify(rows.value, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `logs_${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Logs downloaded");
}

// ── Row style ────────────────────────────────────────────────────

function rowClass(entry: LogEntry): string {
    switch (entry.level) {
        case "ERROR":
        case "CRITICAL":
            return "log-row--error";
        case "WARNING":
            return "log-row--warning";
        default:
            return "";
    }
}

// ── Render expanded detail for access-log entries ────────────────

function renderMessage(entry: LogEntry) {
    // Access log entries have extra fields (method, path, status, duration_ms)
    if (entry.method && entry.path && entry.status !== undefined) {
        const statusColor =
            entry.status >= 500
                ? "error"
                : entry.status >= 400
                  ? "warning"
                  : "success";
        return h(NSpace, { size: [4, 0], wrap: false }, () => [
            h(
                NTag,
                { type: statusColor, size: "tiny" },
                () => `${entry.status}`,
            ),
            h(NText, { depth: 2 }, () => `${entry.method}`),
            h(NText, { depth: 1 }, () => entry.path ?? ""),
            h(NText, { depth: 3 }, () => `${entry.duration_ms?.toFixed(1)}ms`),
        ]);
    }
    return h(NText, { depth: 2 }, () => entry.message);
}

// ── Connection indicator ─────────────────────────────────────────

const connLabel = computed(() =>
    connected.value ? "Connected" : paused.value ? "Paused" : "Reconnecting…",
);
const connColor = computed(() =>
    connected.value
        ? ("success" as const)
        : paused.value
          ? ("warning" as const)
          : ("error" as const),
);
</script>

<template>
    <NCard title="Live Log Tail" size="small">
        <!-- Toolbar: filters + actions -->
        <NSpace align="center" style="margin-bottom: 16px" :wrap="true">
            <NSelect
                v-model:value="level"
                :options="LEVEL_OPTIONS"
                size="small"
                style="width: 130px"
                placeholder="Level"
                clearable
            />
            <NInput
                v-model:value="substring"
                size="small"
                style="width: 200px"
                placeholder="Substring…"
                clearable
            />
            <NInput
                v-model:value="requestIdFilter"
                size="small"
                style="width: 270px"
                placeholder="Request ID…"
                clearable
            />

            <NTag :type="connColor" size="small">
                {{ connLabel }}
            </NTag>
            <NText depth="3" style="font-size: 12px">
                {{ rows.length.toLocaleString() }} entries
                <template v-if="paused && pending.length > 0">
                    · {{ pending.length.toLocaleString() }} buffered
                </template>
            </NText>

            <div style="flex: 1" />

            <NButton size="small" @click="togglePause">
                {{ paused ? "Resume" : "Pause" }}
            </NButton>
            <NButton size="small" @click="handleClear"> Clear </NButton>
            <NButton size="small" @click="handleDownload"> Download </NButton>
        </NSpace>

        <!-- Log table -->
        <NScrollbar style="max-height: calc(100vh - 280px)">
            <table class="log-table">
                <thead>
                    <tr>
                        <th class="col-time">Time</th>
                        <th class="col-level">Level</th>
                        <th class="col-logger">Logger</th>
                        <th class="col-message">Message</th>
                        <th class="col-rid">Request ID</th>
                    </tr>
                </thead>
                <tbody>
                    <tr
                        v-for="(entry, i) in rows"
                        :key="i"
                        :class="rowClass(entry)"
                    >
                        <td class="col-time">
                            <NText depth="3" style="font-size: 12px">
                                {{ fmtTime(entry.timestamp) }}
                            </NText>
                        </td>
                        <td class="col-level">
                            <NTag
                                :type="LEVEL_COLORS[entry.level] ?? 'default'"
                                size="tiny"
                            >
                                {{ entry.level }}
                            </NTag>
                        </td>
                        <td class="col-logger">
                            <NText depth="3" style="font-size: 12px">
                                {{ entry.logger }}
                            </NText>
                        </td>
                        <td class="col-message">
                            <component :is="renderMessage(entry)" />
                            <div v-if="entry.exc_info" class="exc-info">
                                <pre>{{ entry.exc_info }}</pre>
                            </div>
                        </td>
                        <td class="col-rid">
                            <NText
                                v-if="entry.request_id"
                                depth="3"
                                style="font-size: 11px; font-family: monospace"
                            >
                                {{ entry.request_id.slice(0, 8) }}
                            </NText>
                        </td>
                    </tr>
                    <tr v-if="rows.length === 0">
                        <td colspan="5" class="empty-row">
                            <NText v-if="!snapshotReceived" depth="3">
                                Connecting…
                            </NText>
                            <NText v-else depth="3">
                                No matching log entries.
                            </NText>
                        </td>
                    </tr>
                </tbody>
            </table>
        </NScrollbar>
    </NCard>
</template>

<style scoped>
.log-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    table-layout: fixed;
}

.log-table thead {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--n-color);
}

.log-table th {
    text-align: left;
    padding: 6px 8px;
    font-weight: 600;
    color: var(--n-text-color-2);
    border-bottom: 1px solid var(--n-border-color);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.log-table td {
    padding: 4px 8px;
    border-bottom: 1px solid var(--n-border-color);
    vertical-align: top;
}

.col-time {
    width: 90px;
}
.col-level {
    width: 80px;
}
.col-logger {
    width: 140px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.col-message {
    width: auto;
}
.col-rid {
    width: 80px;
}

.log-row--error {
    background: rgba(255, 90, 90, 0.08);
}
.log-row--warning {
    background: rgba(255, 200, 50, 0.05);
}

.empty-row {
    text-align: center;
    padding: 40px 0;
}

.exc-info {
    margin-top: 4px;
}
.exc-info pre {
    margin: 0;
    font-size: 11px;
    color: var(--n-text-color-3);
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 120px;
    overflow-y: auto;
}
</style>
