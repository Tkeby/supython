import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import AppShell from "@/components/shell/AppShell.vue";

declare module "vue-router" {
  interface RouteMeta {
    requiresAuth?: boolean;
  }
}

const routes = [
  { path: "/login", component: () => import("@/views/LoginView.vue") },
  {
    path: "/",
    component: AppShell,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        name: "dashboard",
        component: () => import("@/views/DashboardView.vue"),
      },
      {
        path: "db/schema",
        component: () => import("@/views/db/SchemaBrowser.vue"),
      },
      {
        path: "db/sql",
        component: () => import("@/views/db/SqlWorkspace.vue"),
      },
      {
        path: "db/tables/:schema/:table",
        component: () => import("@/views/db/TableData.vue"),
      },
      { path: "db/rls", component: () => import("@/views/db/RlsEditor.vue") },
      {
        path: "db/migrations",
        component: () => import("@/views/db/Migrations.vue"),
      },
      { path: "auth/users", component: () => import("@/views/auth/Users.vue") },
      {
        path: "auth/tokens",
        component: () => import("@/views/auth/RefreshTokens.vue"),
      },
      { path: "auth/audit", component: () => import("@/views/auth/Audit.vue") },
      {
        path: "auth/templates",
        component: () => import("@/views/auth/Templates.vue"),
      },
      {
        path: "storage",
        component: () => import("@/views/storage/Buckets.vue"),
      },
      {
        path: "storage/:bucket",
        component: () => import("@/views/storage/ObjectBrowser.vue"),
      },
      {
        path: "functions",
        component: () => import("@/views/functions/Routes.vue"),
      },
      {
        path: "functions/invoke/:name(.*)",
        component: () => import("@/views/functions/Invoke.vue"),
      },
      {
        path: "realtime",
        component: () => import("@/views/realtime/Channels.vue"),
      },
      {
        path: "jobs/queue",
        component: () => import("@/views/jobs/Queue.vue"),
      },
      {
        path: "jobs/crons",
        component: () => import("@/views/jobs/Crons.vue"),
      },
      {
        path: "ops/backups",
        component: () => import("@/views/ops/Backups.vue"),
      },
      { path: "ops/logs", component: () => import("@/views/ops/Logs.vue") },
    ],
  },
];

const router = createRouter({ history: createWebHistory("/admin/"), routes });

router.beforeEach(async (to) => {
  if (!to.meta.requiresAuth) return true;
  const auth = useAuthStore();
  if (!auth.session) await auth.hydrate();
  return auth.session ? true : { path: "/login", query: { next: to.fullPath } };
});

export default router;
