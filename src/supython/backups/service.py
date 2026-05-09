"""Framework-agnostic async service functions for the backups module.

All functions take an asyncpg.Connection and raise BackupError on failure.
No FastAPI imports here — this module is testable without HTTP.

Backups execute via the jobs framework (see ``_backup_job.py``); this
module is responsible for the admin.backups bookkeeping and for
enqueueing the work. The jobs worker is the durable executor.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import asyncpg

from ..settings import get_settings
from .schemas import BackupRecord

logger = logging.getLogger(__name__)

_VALID_KINDS = ("full", "schema-only")


class BackupError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _get_backups_dir() -> Path:
    s = get_settings()
    return Path(s.backups_dir).resolve()


def _parse_db_url(db_url: str) -> dict[str, str]:
    parsed = urlparse(db_url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "",
        "password": parsed.password or "",
        "dbname": (parsed.path or "/").lstrip("/") or "supython",
    }


def _row_to_record(row: asyncpg.Record) -> BackupRecord:
    return BackupRecord(
        id=row["id"],
        kind=row["kind"],
        status=row["status"],
        size=row.get("size"),
        file_path=row.get("file_path"),
        error_message=row.get("error_message"),
        started_at=row["started_at"],
        finished_at=row.get("finished_at"),
        created_at=row["created_at"],
    )


async def start_backup(conn: asyncpg.Connection, *, kind: str) -> BackupRecord:
    """Insert a backup row and enqueue a job to execute the dump.

    Returns the initial record immediately. The jobs worker picks up the
    queued job, runs pg_dump, and updates admin.backups status/size/file_path
    when done. If a worker dies mid-job the visibility timeout reclaims it.
    """
    if kind not in _VALID_KINDS:
        raise BackupError(
            "invalid_kind",
            f"kind must be one of {_VALID_KINDS}",
            422,
        )

    row = await conn.fetchrow(
        """
        insert into admin.backups (kind)
        values ($1)
        returning id, kind, status, size, file_path, error_message,
                  started_at, finished_at, created_at
        """,
        kind,
    )
    if row is None:
        raise BackupError("insert_failed", "Failed to create backup row", 500)
    record = _row_to_record(row)

    backups_dir = _get_backups_dir()
    backups_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = ".ddl.sql" if kind == "schema-only" else ".sql"
    filename = f"backup_{record.id}_{kind}_{timestamp}{suffix}"
    file_path = str(backups_dir / filename)

    # Avoid an import cycle: jobs.service is imported lazily because
    # ``jobs/__init__`` re-exports the admin router which can transitively
    # touch this module.
    from ..jobs.service import enqueue
    from ._backup_job import JOB_NAME

    await enqueue(
        conn,
        name=JOB_NAME,
        payload={
            "backup_id": str(record.id),
            "kind": kind,
            "file_path": file_path,
        },
        idempotency_key=f"admin_backup:{record.id}",
    )

    return record


async def list_backups(
    conn: asyncpg.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[BackupRecord]:
    rows = await conn.fetch(
        """
        select id, kind, status, size, file_path, error_message,
               started_at, finished_at, created_at
        from admin.backups
        order by created_at desc
        limit $1 offset $2
        """,
        limit,
        offset,
    )
    return [_row_to_record(r) for r in rows]


async def get_backup(conn: asyncpg.Connection, backup_id: UUID) -> BackupRecord | None:
    row = await conn.fetchrow(
        """
        select id, kind, status, size, file_path, error_message,
               started_at, finished_at, created_at
        from admin.backups
        where id = $1
        """,
        backup_id,
    )
    return _row_to_record(row) if row else None


async def count_backups(conn: asyncpg.Connection) -> int:
    val = await conn.fetchval("select count(*) from admin.backups")
    return val or 0


_SIGNED_URL_TTL_S = 600  # 10 minutes


def _signing_secret() -> str:
    """Derive a signing secret from the storage signed URL secret.

    Falls back to a hard-coded dev value when the secret is not configured
    (mirrors the storage module's dev-friendly posture).
    """
    s = get_settings()
    secret = s.storage_signed_url_secret
    if secret is None:
        logger.warning(
            "backups: STORAGE_SIGNED_URL_SECRET not set; "
            "download tokens are trivially forgeable in dev mode"
        )
        return "backups-dev-secret-not-for-production"
    return f"backups:{secret}"


def generate_download_token(backup_id: UUID) -> str:
    """Generate a time-limited HMAC token for downloading a backup file.

    Returns an opaque string that embeds the backup_id, expiry, and HMAC
    signature. Valid for _SIGNED_URL_TTL_S seconds.
    """
    expires_at = int(time.time()) + _SIGNED_URL_TTL_S
    payload = f"{backup_id}:{expires_at}"
    secret = _signing_secret()
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = f"{backup_id}:{expires_at}:{sig}"
    return token


def verify_download_token(token: str) -> UUID | None:
    """Verify a download token. Returns the backup_id if valid, None otherwise."""
    parts = token.split(":")
    if len(parts) != 3:
        return None
    backup_id_str, expires_str, sig = parts
    try:
        expires_at = int(expires_str)
    except ValueError:
        return None
    if time.time() > expires_at:
        return None
    payload = f"{backup_id_str}:{expires_at}"
    secret = _signing_secret()
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        return UUID(backup_id_str)
    except ValueError:
        return None
