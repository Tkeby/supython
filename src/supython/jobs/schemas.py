"""Pydantic v2 models for the jobs module."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EnqueueRequest(BaseModel):
    name: str
    payload: dict | None = None
    queue: str = "default"
    idempotency_key: str | None = None
    user_id: UUID | None = None
    max_attempts: int = 3
    backoff: str = "exponential"
    backoff_base_s: float = 5.0
    backoff_max_s: float = 300.0
    run_at: datetime | None = None
    version: int = 1
    role: str = "service_role"
    claims_from: str | None = None


class JobRecord(BaseModel):
    id: UUID
    name: str
    version: int = 1
    payload: dict | None = None
    queue: str = "default"
    idempotency_key: str | None = None
    user_id: UUID | None = None
    status: str = "queued"
    attempts: int = 0
    max_attempts: int = 3
    backoff: str = "exponential"
    backoff_base_s: float = 5.0
    backoff_max_s: float = 300.0
    run_at: datetime | None = None
    locked_at: datetime | None = None
    locked_by: str | None = None
    role: str = "service_role"
    claims_from: str | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    last_error: str | None = None


class EnqueueResult(BaseModel):
    job: JobRecord
    is_new: bool


class JobResponse(BaseModel):
    id: UUID
    name: str
    version: int = 1
    status: str
    payload: dict | None = None
    queue: str = "default"
    user_id: UUID | None = None
    attempts: int = 0
    max_attempts: int = 3
    run_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    last_error: str | None = None


class JobFilter(BaseModel):
    status: str | None = None
    queue: str | None = None
    name: str | None = None
    user_id: UUID | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class CronDefinitionSchema(BaseModel):
    name: str
    cron_expr: str
    job_name: str
    job_version: int = 1
    payload: dict | None = None
    queue: str = "default"
    enabled: bool = True


class BackendHealth(BaseModel):
    backend: str
    healthy: bool
    detail: str | None = None
