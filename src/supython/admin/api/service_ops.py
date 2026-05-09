"""Admin service layer for the ops backups + live log tail surface.

Pure async functions over ``asyncpg.Connection``. No FastAPI imports.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from ...backups import service as backups_service
from ...logging_config import get_log_ring
from ..errors import AdminError
from ..schemas import AdminBackupRow, AdminBackupsPage, BackupDownloadResponse

logger = logging.getLogger(__name__)


def _row_to_admin_backup(row: asyncpg.Record) -> AdminBackupRow:
    return AdminBackupRow(
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


async def list_backups(
    conn: asyncpg.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
) -> AdminBackupsPage:
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
    total = await conn.fetchval("select count(*) from admin.backups")
    return AdminBackupsPage(
        rows=[_row_to_admin_backup(r) for r in rows],
        total=total or 0,
    )


async def start_backup(conn: asyncpg.Connection, *, kind: str) -> AdminBackupRow:
    try:
        record = await backups_service.start_backup(conn, kind=kind)
    except backups_service.BackupError as exc:
        raise AdminError(exc.code, exc.message, exc.status) from exc

    # Re-fetch to get the row in admin shape
    row = await conn.fetchrow(
        """
        select id, kind, status, size, file_path, error_message,
               started_at, finished_at, created_at
        from admin.backups
        where id = $1
        """,
        record.id,
    )
    if row is None:
        raise AdminError("backup_not_found", "backup not found after creation", 500)
    return _row_to_admin_backup(row)


async def get_backup_download_response(
    conn: asyncpg.Connection, backup_id: UUID
) -> BackupDownloadResponse:
    row = await conn.fetchrow(
        """
        select id, status, file_path
        from admin.backups
        where id = $1
        """,
        backup_id,
    )
    if row is None:
        raise AdminError("backup_not_found", f"backup {backup_id} not found", 404)
    if row["status"] != "completed":
        raise AdminError(
            "backup_not_ready",
            f"backup status is {row['status']!r}, not 'completed'",
            409,
        )
    if not row["file_path"]:
        raise AdminError(
            "backup_no_file",
            "backup has no file_path",
            500,
        )

    token = backups_service.generate_download_token(backup_id)
    download_url = f"/admin/api/v1/ops/downloads/{token}"

    return BackupDownloadResponse(
        download_url=download_url,
        expires_in=600,
        backup_id=backup_id,
    )


# ---------------------------------------------------------------------------
# Live log tail
# ---------------------------------------------------------------------------

_LOG_LEVEL_RANK: dict[str, int] = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


def _entry_matches(
    entry: dict[str, object],
    *,
    level: str | None,
    substring: str | None,
    request_id: str | None,
) -> bool:
    if level is not None:
        min_rank = _LOG_LEVEL_RANK.get(level.upper(), 0)
        entry_rank = _LOG_LEVEL_RANK.get(str(entry.get("level", "")), 0)
        if entry_rank < min_rank:
            return False
    if substring is not None:
        msg = str(entry.get("message", ""))
        if substring.lower() not in msg.lower():
            return False
    if request_id is not None:
        entry_rid = str(entry.get("request_id", ""))
        if request_id != entry_rid:
            return False
    return True


_LOG_TAIL_POLL_S = 0.5
_LOG_TAIL_KEEPALIVE_S = 15.0


async def tail_logs(
    *,
    level: str | None = None,
    substring: str | None = None,
    request_id: str | None = None,
) -> AsyncIterator[str]:
    """SSE event-stream generator that tails the in-memory log ring buffer.

    On first iteration it emits a ``logs:snapshot`` event with all matching
    entries.  Subsequent iterations poll the ring buffer and emit
    ``logs:append`` events for any new matching entries.

    A keepalive ``:`` comment line is emitted every 15 s to prevent proxies
    from closing the connection.
    """
    last_ts: str = ""
    last_keepalive = datetime.now(tz=UTC)

    while True:
        all_entries = get_log_ring()

        # Find the slice of entries that arrived after the last timestamp we saw.
        # Walk from the right (newest) to find where to start.
        if last_ts:
            new_entries: list[dict[str, object]] = []
            for entry in reversed(all_entries):
                if str(entry.get("timestamp", "")) <= last_ts:
                    break
                new_entries.append(entry)
            new_entries.reverse()
        else:
            # First poll — always emit a snapshot so clients know the
            # handshake is complete, even when filters exclude every entry.
            matching = [
                e
                for e in all_entries
                if _entry_matches(e, level=level, substring=substring, request_id=request_id)
            ]
            yield f"event: logs:snapshot\ndata: {json.dumps(matching)}\n\n"
            last_ts = str(all_entries[-1].get("timestamp", "")) if all_entries else ""
            continue
        # Emit matching new entries as `logs:append` events.
        for entry in new_entries:
            if _entry_matches(entry, level=level, substring=substring, request_id=request_id):
                yield f"event: logs:append\ndata: {json.dumps(entry)}\n\n"

        if new_entries:
            last_ts = str(new_entries[-1].get("timestamp", ""))

        # Keepalive
        now = datetime.now(tz=UTC)
        if (now - last_keepalive).total_seconds() >= _LOG_TAIL_KEEPALIVE_S:
            yield ": keepalive\n\n"
            last_keepalive = now

        await asyncio.sleep(_LOG_TAIL_POLL_S)
