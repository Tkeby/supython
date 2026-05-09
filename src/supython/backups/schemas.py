"""Pydantic v2 models for the backups module."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BackupRecord(BaseModel):
    id: UUID
    kind: str
    status: str
    size: int | None = None
    file_path: str | None = None
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime
