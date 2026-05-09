export interface TablePage {
  columns: string[];
  rows: unknown[][];
  total: number;
}

export interface SqlResult {
  columns: string[];
  rows: unknown[][];
  row_count: number;
}

export interface DryRunResponse {
  columns: string[];
  rows: unknown[][];
}

export interface RlsPolicy {
  schemaname: string;
  tablename: string;
  policyname: string;
  permissive: "PERMISSIVE" | "RESTRICTIVE";
  roles: string[];
  cmd: "SELECT" | "INSERT" | "UPDATE" | "DELETE" | "ALL";
  qual: string | null;
  with_check: string | null;
}

export type AdminUser = {
  id: string;
  email: string;
  created_at: string;
  last_sign_in_at: string | null;
  banned_until: string | null;
  email_confirmed_at: string | null;
};

export interface Identity {
  id: string;
  user_id: string;
  provider: string;
  provider_user_id: string;
  identity_data: Record<string, unknown>;
  created_at: string;
}

export interface AuditEvent {
  id: string;
  user_id: string | null;
  event: string;
  ip: string | null;
  ua: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface AdminUserDetail {
  user: AdminUser;
  identities: Identity[];
  recent_audit: AuditEvent[];
}

export type RefreshToken = {
  id: number;
  user_id: string;
  token: string;
  parent: string | null;
  revoked: boolean;
  created_at: string;
};

export type AdminAuditEvent = {
  id: string;
  user_id: string | null;
  event: string;
  ip: string | null;
  ua: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type EmailTemplate = {
  name: string;
  subject: string;
  text_body: string;
  updated_at: string;
};

export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type AdminJobRow = {
  id: string;
  name: string;
  version: number;
  status: JobStatus;
  payload: Record<string, unknown> | null;
  queue: string;
  user_id: string | null;
  attempts: number;
  max_attempts: number;
  run_at: string | null;
  locked_at: string | null;
  locked_by: string | null;
  role: string;
  finished_at: string | null;
  created_at: string | null;
  last_error: string | null;
};

export type AdminJobsPage = {
  rows: AdminJobRow[];
  total: number;
  counts: Record<string, number>;
};

export type AdminCronRow = {
  id: string;
  name: string;
  cron_expr: string;
  job_name: string;
  job_version: number;
  payload: Record<string, unknown> | null;
  queue: string;
  enabled: boolean;
  last_fire_at: string | null;
  created_at: string | null;
  pg_cron_active: boolean | null;
};

export type PgCronHealth = {
  installed: boolean;
  active_jobs: number;
  extension_version: string | null;
};

/** @deprecated Use AdminJobRow instead. */
export interface Job {
  id: string;
  queue_name: string;
  status: JobStatus;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  error: string | null;
}

/** @deprecated Use AdminCronRow instead. */
export interface CronJob {
  jobid: number;
  schedule: string;
  command: string;
  nodename: string;
  active: boolean;
  jobname: string | null;
}

export interface AdminBucket {
  id: string;
  name: string;
  owner: string | null;
  public: boolean;
  object_count: number;
  total_size: number;
  file_size_limit: number | null;
  allowed_mime_types: string[] | null;
  created_at: string;
  updated_at: string;
}

export type AdminObject = {
  id: string;
  bucket: string;
  name: string;
  owner: string;
  size: number;
  mime_type: string | null;
  etag: string | null;
  created_at: string;
  updated_at: string;
};

export interface AdminObjectsPage {
  rows: AdminObject[];
  total: number;
  prefix: string | null;
}

export type SignRole = "service_role" | "authenticated" | "anon";

export interface AdminSignedUrlResponse {
  signed_url: string;
  token: string;
  expires_at: string;
  expires_in: number;
  signed_under_role: string;
}

export type FunctionRoute = {
  name: string;
  path: string;
  methods: string[];
  auth: "authenticated" | "anon";
};

export type FunctionSourceResponse = {
  name: string;
  path: string;
  source: string;
  size: number;
};

export type FunctionInvokeRequest = {
  method?: string;
  headers?: Record<string, string>;
  body?: unknown;
  query?: string | null;
};

export type FunctionInvokeResponse = {
  status: number;
  headers: Record<string, string>;
  body: unknown | null;
  body_text: string;
  elapsed_ms: number;
};

// ── Realtime ──────────────────────────────────────────────────────

export type EnabledTable = {
  schema_name: string;
  table_name: string;
  pk_columns: string[];
  owner_column: string | null;
  created_at: string;
};

export type RealtimeFrame = {
  event: string;
  topic: string;
  payload: Record<string, unknown>;
  receivedAt: Date;
};

export type BroadcastPayload = {
  topic: string;
  delivered: number;
};

export type AdminBackupRow = {
  id: string;
  kind: string;
  status: string;
  size: number | null;
  file_path: string | null;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
};

export type AdminBackupsPage = {
  rows: AdminBackupRow[];
  total: number;
};

export type BackupDownloadResponse = {
  download_url: string;
  expires_in: number;
  backup_id: string;
};

export type LogEntry = {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
  request_id?: string;
  exc_info?: string;
  duration_ms?: number;
  status?: number;
  method?: string;
  path?: string;
};
