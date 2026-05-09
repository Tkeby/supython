import { api } from "./client";
import type {
  TablePage,
  SqlResult,
  DryRunResponse,
  RlsPolicy,
  AdminUser,
  AdminUserDetail,
  AdminAuditEvent,
  EmailTemplate,
  RefreshToken,
  AdminJobRow,
  AdminJobsPage,
  AdminCronRow,
  PgCronHealth,
  JobStatus,
  AdminBucket,
  AdminObjectsPage,
  AdminSignedUrlResponse,
  SignRole,
  FunctionRoute,
  FunctionSourceResponse,
  FunctionInvokeRequest,
  FunctionInvokeResponse,
  EnabledTable,
  BroadcastPayload,
  AdminBackupRow,
  AdminBackupsPage,
  BackupDownloadResponse,
} from "./types";

function _cleanParams(q: Record<string, unknown>): URLSearchParams {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null || v === "") continue;
    p.set(k, String(v));
  }
  return p;
}

export const dbApi = {
  schemas: () =>
    api.get<{ name: string; owner: string; is_user: boolean }[]>("/db/schemas"),

  tables: (schema: string) =>
    api.get<{ name: string; rls_enabled: boolean }[]>(`/db/tables/${schema}`),

  rows: (schema: string, table: string, q: Record<string, string | number>) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(q)) {
      if (v === "" || v === null || v === undefined) continue;
      params.set(k, String(v));
    }
    return api.get<TablePage>(`/db/tables/${schema}/${table}/rows?${params}`);
  },

  runSql: (statement: string, read_only = true) =>
    api.post<SqlResult>("/db/sql/execute", { statement, read_only }),

  policies: (schema: string, table: string) =>
    api.get<RlsPolicy[]>(`/db/rls/${schema}/${table}`),

  dryRunPolicy: (ddl: string, sample_query: string) =>
    api.post<DryRunResponse>("/db/rls/dry-run", { ddl, sample_query }),

  migrations: () =>
    api.get<{ version: string; applied_at: string; source: string }[]>(
      "/db/migrations",
    ),
};

export const authApi = {
  users: (q: {
    search?: string;
    confirmed?: boolean | null;
    banned?: boolean | null;
    limit?: number;
    offset?: number;
  }) =>
    api.get<{ rows: AdminUser[]; total: number }>(
      `/auth/users?${_cleanParams(q)}`,
    ),

  getUser: (id: string) => api.get<AdminUserDetail>(`/auth/users/${id}`),

  banUser: (id: string, durationSeconds?: number) =>
    api.post(
      `/auth/users/${id}/ban`,
      durationSeconds ? { duration_seconds: durationSeconds } : undefined,
    ),

  unbanUser: (id: string) => api.post(`/auth/users/${id}/unban`),

  forceLogout: (id: string) =>
    api.post<{ revoked: number }>(`/auth/users/${id}/force-logout`),

  refreshTokens: (q: { user_id?: string; limit?: number; offset?: number }) =>
    api.get<{ rows: RefreshToken[]; total: number }>(
      `/auth/refresh-tokens?${_cleanParams(q)}`,
    ),
  revokeToken: (id: number) => api.del(`/auth/refresh-tokens/${id}`),

  audit: (q: {
    event?: string;
    ip?: string;
    from_date?: string;
    to_date?: string;
    limit?: number;
    offset?: number;
  }) =>
    api.get<{ rows: AdminAuditEvent[]; total: number }>(
      `/auth/audit?${_cleanParams(q)}`,
    ),

  templates: () => api.get<EmailTemplate[]>("/auth/templates"),

  updateTemplate: (
    name: string,
    body: { subject?: string; text_body?: string },
  ) => api.patch<EmailTemplate>(`/auth/templates/${name}`, body),

  session: () =>
    api.get<{ admin_id: string; email: string; expires_at: string }>(
      "/auth/session",
    ),
};

export const storageApi = {
  buckets: () => api.get<AdminBucket[]>("/storage/buckets"),

  objects: (
    bucket: string,
    q: { prefix?: string; limit?: number; offset?: number },
  ) =>
    api.get<AdminObjectsPage>(
      `/storage/buckets/${bucket}/objects?${_cleanParams(q)}`,
    ),

  sign: (
    objectId: string,
    expiresIn: number,
    role?: SignRole,
    impersonateSub?: string,
  ) =>
    api.post<AdminSignedUrlResponse>(`/storage/objects/${objectId}/sign`, {
      expires_in: expiresIn,
      role: role ?? "service_role",
      impersonate_sub: impersonateSub || undefined,
    }),

  deleteObject: (objectId: string) => api.del(`/storage/objects/${objectId}`),
};

export const functionsApi = {
  routes: () => api.get<FunctionRoute[]>("/functions/routes"),

  source: (name: string) =>
    api.get<FunctionSourceResponse>(
      `/functions/${encodeURIComponent(name)}/source`,
    ),

  invoke: (name: string, payload: FunctionInvokeRequest) =>
    api.post<FunctionInvokeResponse>(
      `/functions/${encodeURIComponent(name)}/invoke`,
      payload,
    ),
};

export const realtimeApi = {
  tables: () => api.get<EnabledTable[]>("/realtime/tables"),

  channels: () =>
    api.get<{ name: string; joined_at: string }[]>("/realtime/channels"),

  broadcast: (topic: string, event: string, payload: Record<string, unknown>) =>
    api.post<BroadcastPayload>("/realtime/broadcast", {
      topic,
      event,
      payload,
    }),
};

export const jobsApi = {
  queue: (q: {
    status?: JobStatus;
    queue?: string;
    limit?: number;
    offset?: number;
  }) => api.get<AdminJobsPage>(`/jobs/queue?${_cleanParams(q)}`),

  retry: (id: string) => api.post<AdminJobRow>(`/jobs/${id}/retry`),

  cancel: (id: string) => api.post<AdminJobRow>(`/jobs/${id}/cancel`),

  crons: () => api.get<AdminCronRow[]>("/jobs/crons"),

  cronHealth: () => api.get<PgCronHealth>("/jobs/crons/health"),

  runCronNow: (name: string) =>
    api.post<AdminJobRow>(`/jobs/crons/${encodeURIComponent(name)}/run-now`),
};

export const systemApi = {
  status: () =>
    api.get<{
      pool_size: number;
      jwks_kid: string;
      broker: boolean;
      jobs: boolean;
    }>("/system/status"),
};

export const opsApi = {
  backups: (q: { limit?: number; offset?: number }) =>
    api.get<AdminBackupsPage>(`/ops/backups?${_cleanParams(q)}`),

  startBackup: (kind: "full" | "schema-only") =>
    api.post<AdminBackupRow>("/ops/backups", { kind }),

  downloadUrl: (backupId: string) =>
    api.get<BackupDownloadResponse>(`/ops/backups/${backupId}/download`),
};
