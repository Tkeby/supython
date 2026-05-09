from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SessionResponse(BaseModel):
    admin_id: UUID
    email: str
    expires_at: datetime


class SchemaInfo(BaseModel):
    name: str
    owner: str
    is_user: bool


class TableInfo(BaseModel):
    name: str
    rls_enabled: bool


class RowsPage(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    total: int


class SqlExecRequest(BaseModel):
    statement: str
    read_only: bool = True


class SqlExecResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int


class DryRunRequest(BaseModel):
    ddl: str
    sample_query: str


class DryRunResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]


class RlsPolicy(BaseModel):
    schemaname: str
    tablename: str
    policyname: str
    permissive: str | None = None
    roles: list[str] | None = None
    cmd: str | None = None
    qual: str | None = None
    with_check: str | None = None


class MigrationRecord(BaseModel):
    version: str
    applied_at: datetime | None = None
    source: str


class SystemStatus(BaseModel):
    pool_size: int
    jwks_kid: str
    broker: bool
    jobs: bool


class SystemVersion(BaseModel):
    version: str


class AdminUser(BaseModel):
    id: UUID
    email: str
    created_at: datetime
    last_sign_in_at: datetime | None = None
    banned_until: datetime | None = None
    email_confirmed_at: datetime | None = None


class AdminUsersPage(BaseModel):
    rows: list[AdminUser]
    total: int


class Identity(BaseModel):
    id: UUID
    user_id: UUID
    provider: str
    provider_user_id: str
    identity_data: dict[str, Any]
    created_at: datetime


class AuditEvent(BaseModel):
    id: UUID
    user_id: UUID | None = None
    event: str
    ip: str | None = None
    ua: str | None = None
    payload: dict[str, Any]
    created_at: datetime


class AdminUserDetail(BaseModel):
    user: AdminUser
    identities: list[Identity]
    recent_audit: list[AuditEvent]


class BanRequest(BaseModel):
    duration_seconds: int | None = None


class RefreshToken(BaseModel):
    id: int
    user_id: UUID
    token: str
    parent: str | None = None
    revoked: bool
    created_at: datetime


class RefreshTokensPage(BaseModel):
    rows: list[RefreshToken]
    total: int


class AdminAuditPage(BaseModel):
    rows: list[AuditEvent]
    total: int


class EmailTemplate(BaseModel):
    name: str
    subject: str
    text_body: str
    updated_at: datetime


class EmailTemplateUpdate(BaseModel):
    subject: str | None = None
    text_body: str | None = None


class AdminBucket(BaseModel):
    id: UUID
    name: str
    owner: UUID | None = None
    public: bool
    object_count: int
    total_size: int
    file_size_limit: int | None = None
    allowed_mime_types: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class AdminObject(BaseModel):
    id: UUID
    bucket: str
    name: str
    owner: UUID
    size: int
    mime_type: str | None = None
    etag: str | None = None
    created_at: datetime
    updated_at: datetime


class AdminObjectsPage(BaseModel):
    rows: list[AdminObject]
    total: int
    prefix: str | None = None


class AdminSignObjectRequest(BaseModel):
    expires_in: int | None = Field(default=None, ge=1)
    role: Literal["service_role", "authenticated", "anon"] = "service_role"
    impersonate_sub: UUID | None = None


class AdminSignedUrlResponse(BaseModel):
    signed_url: str
    token: str
    expires_at: datetime
    expires_in: int
    signed_under_role: str


class FunctionRoute(BaseModel):
    name: str
    path: str
    methods: list[str]
    auth: Literal["authenticated", "anon"]


class FunctionSourceResponse(BaseModel):
    name: str
    path: str
    source: str
    size: int


class FunctionInvokeRequest(BaseModel):
    method: str = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any | None = None
    query: str | None = None


class FunctionInvokeResponse(BaseModel):
    status: int
    headers: dict[str, str]
    body: Any | None = None
    body_text: str
    elapsed_ms: float


class AdminBroadcastRequest(BaseModel):
    """Body for POST /admin/api/v1/realtime/broadcast."""

    topic: str = Field(min_length=1)
    event: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)


class AdminJobRow(BaseModel):
    id: UUID
    name: str
    version: int = 1
    status: str
    payload: dict[str, Any] | None = None
    queue: str = "default"
    user_id: UUID | None = None
    attempts: int = 0
    max_attempts: int = 3
    run_at: datetime | None = None
    locked_at: datetime | None = None
    locked_by: str | None = None
    role: str = "service_role"
    finished_at: datetime | None = None
    created_at: datetime | None = None
    last_error: str | None = None


class AdminJobsPage(BaseModel):
    rows: list[AdminJobRow]
    total: int
    counts: dict[str, int] = {}


class AdminCronRow(BaseModel):
    id: UUID
    name: str
    cron_expr: str
    job_name: str
    job_version: int = 1
    payload: dict[str, Any] | None = None
    queue: str = "default"
    enabled: bool = True
    last_fire_at: datetime | None = None
    created_at: datetime | None = None
    pg_cron_active: bool | None = None


class PgCronHealth(BaseModel):
    installed: bool
    active_jobs: int = 0
    extension_version: str | None = None


class AdminBackupRow(BaseModel):
    id: UUID
    kind: str
    status: str
    size: int | None = None
    file_path: str | None = None
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime


class AdminBackupsPage(BaseModel):
    rows: list[AdminBackupRow]
    total: int


class StartBackupRequest(BaseModel):
    kind: Literal["full", "schema-only"] = "full"


class BackupDownloadResponse(BaseModel):
    download_url: str
    expires_in: int
    backup_id: UUID
