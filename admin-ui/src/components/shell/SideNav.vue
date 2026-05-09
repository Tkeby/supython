<script setup lang="ts">
import { computed, h } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NMenu, NIcon } from "naive-ui";
import type { MenuOption } from "naive-ui";

const route = useRoute();
const router = useRouter();

type SvgEl = [string, Record<string, any>];

interface NavItem {
    label: string;
    key: string;
    path?: string;
    icon: () => any;
    children?: NavItem[];
}

function iconRender(els: SvgEl[]) {
    return () =>
        h(NIcon, null, {
            default: () =>
                h(
                    "svg",
                    {
                        width: 18,
                        height: 18,
                        viewBox: "0 0 24 24",
                        fill: "none",
                        stroke: "currentColor",
                        "stroke-width": 2,
                    },
                    els.map(([tag, attrs]) => h(tag, attrs)),
                ),
        });
}

function toMenuOption(item: NavItem): MenuOption {
    const opt: MenuOption = {
        label: item.label,
        key: item.key,
        icon: item.icon,
    };
    if (item.children) {
        opt.children = item.children.map(toMenuOption);
    }
    return opt;
}

function findNavItem(key: string, items: NavItem[]): NavItem | undefined {
    for (const item of items) {
        if (item.key === key) return item;
        if (item.children) {
            const found = findNavItem(key, item.children);
            if (found) return found;
        }
    }
    return undefined;
}

const navItems: NavItem[] = [
    {
        label: "Dashboard",
        key: "dashboard",
        path: "/",
        icon: iconRender([
            ["rect", { x: 3, y: 3, width: 7, height: 7, rx: 1 }],
            ["rect", { x: 14, y: 3, width: 7, height: 7, rx: 1 }],
            ["rect", { x: 14, y: 14, width: 7, height: 7, rx: 1 }],
            ["rect", { x: 3, y: 14, width: 7, height: 7, rx: 1 }],
        ]),
    },
    {
        label: "Database",
        key: "database",
        path: "/db/schema",
        icon: iconRender([
            ["ellipse", { cx: 12, cy: 5, rx: 9, ry: 3 }],
            ["path", { d: "M3 5v14a9 3 0 009 3 9 3 0 009-3V5" }],
            ["path", { d: "M3 12a9 3 0 009 3 9 3 0 009-3" }],
        ]),
    },
    {
        label: "Auth",
        key: "auth",
        icon: iconRender([
            ["rect", { x: 3, y: 11, width: 18, height: 11, rx: 2 }],
            ["path", { d: "M7 11V7a5 5 0 0110 0v4" }],
        ]),
        children: [
            {
                label: "Users",
                key: "auth-users",
                path: "/auth/users",
                icon: iconRender([]),
            },
            {
                label: "Refresh Tokens",
                key: "auth-tokens",
                path: "/auth/tokens",
                icon: iconRender([]),
            },
            {
                label: "Audit Log",
                key: "auth-audit",
                path: "/auth/audit",
                icon: iconRender([]),
            },
            {
                label: "Email Templates",
                key: "auth-templates",
                path: "/auth/templates",
                icon: iconRender([]),
            },
        ],
    },
    {
        label: "Storage",
        key: "storage",
        path: "/storage",
        icon: iconRender([
            [
                "path",
                {
                    d: "M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z",
                },
            ],
        ]),
    },
    {
        label: "Functions",
        key: "functions",
        path: "/functions",
        icon: iconRender([
            ["polyline", { points: "4 17 10 11 4 5" }],
            ["line", { x1: 12, y1: 19, x2: 20, y2: 19 }],
        ]),
    },
    {
        label: "Realtime",
        key: "realtime",
        path: "/realtime",
        icon: iconRender([["path", { d: "M13 2L3 14h9l-1 8 10-12h-9l1-8z" }]]),
    },
    {
        label: "Jobs",
        key: "jobs",
        icon: iconRender([
            ["circle", { cx: 12, cy: 12, r: 10 }],
            ["polyline", { points: "12 6 12 12 16 14" }],
        ]),
        children: [
            {
                label: "Queue",
                key: "jobs-queue",
                path: "/jobs/queue",
                icon: iconRender([]),
            },
            {
                label: "Crons",
                key: "jobs-crons",
                path: "/jobs/crons",
                icon: iconRender([]),
            },
        ],
    },

    {
        label: "Ops",
        key: "ops",
        icon: iconRender([
            ["circle", { cx: 12, cy: 12, r: 3 }],
            [
                "path",
                {
                    d: "M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.68 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z",
                },
            ],
        ]),
        children: [
            {
                label: "Backups",
                key: "ops-backups",
                path: "/ops/backups",
                icon: iconRender([]),
            },
            {
                label: "Logs",
                key: "ops-logs",
                path: "/ops/logs",
                icon: iconRender([]),
            },
        ],
    },
];

const menuOptions: MenuOption[] = navItems.map(toMenuOption);

const activeKey = computed(() => {
    const path = route.path;
    function match(items: NavItem[]): string | null {
        for (const item of items) {
            if (
                item.path &&
                (path === item.path || path.startsWith(item.path + "/"))
            ) {
                return item.key;
            }
            if (item.children) {
                const childMatch = match(item.children);
                if (childMatch) return childMatch;
            }
        }
        return null;
    }
    return match(navItems);
});

function handleSelect(key: string) {
    const item = findNavItem(key, navItems);
    if (item?.path) {
        router.push(item.path);
    }
}

const footerOptions: MenuOption[] = [
    {
        label: "Docs",
        key: "docs",
        icon: iconRender([
            ["path", { d: "M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z" }],
            ["path", { d: "M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z" }],
        ]),
    },
    {
        label: "Support",
        key: "support",
        icon: iconRender([
            ["path", { d: "M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z" }],
        ]),
    },
];
</script>

<template>
    <div style="display: flex; flex-direction: column; height: 100%">
        <div
            style="
                padding: 16px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            "
        >
            <div style="display: flex; align-items: center; gap: 12px">
                <div
                    style="
                        width: 32px;
                        height: 32px;
                        border-radius: 6px;
                        background: #10b981;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: #fff;
                        font-weight: 900;
                        font-size: 14px;
                    "
                >
                    S
                </div>
                <div>
                    <div
                        style="
                            color: #10b981;
                            font-weight: 900;
                            font-size: 13px;
                            text-transform: uppercase;
                            letter-spacing: 0.1em;
                        "
                    >
                        supython
                    </div>
                    <div
                        style="
                            color: rgba(255, 255, 255, 0.35);
                            font-size: 11px;
                            text-transform: uppercase;
                            letter-spacing: 0.1em;
                            font-weight: 600;
                        "
                    >
                        Operator Console
                    </div>
                </div>
            </div>
        </div>

        <div style="flex: 1; overflow-y: auto; padding-top: 8px">
            <NMenu
                :value="activeKey"
                :options="menuOptions"
                :collapsed-width="64"
                :indent="18"
                :root-indent="18"
                @update:value="handleSelect"
            />
        </div>

        <div style="border-top: 1px solid rgba(255, 255, 255, 0.06)">
            <NMenu
                :collapsed-width="64"
                :indent="18"
                :root-indent="18"
                :options="footerOptions"
            />
        </div>
    </div>
</template>
