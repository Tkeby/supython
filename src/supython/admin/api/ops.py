"""Admin ops control plane.

GET  /admin/api/v1/ops/backups
    List backups (id, kind, size, started_at, finished_at, status).

POST /admin/api/v1/ops/backups
    Start a new backup (full or schema-only). Returns the record immediately;
    the backup runs in the background.

GET  /admin/api/v1/ops/backups/{id}/download
    Returns a signed download URL with 10 min TTL.

GET  /admin/api/v1/ops/downloads/{token}
    Streams the backup file after verifying the signed token.
    Does NOT require admin session — the token is the authority.

GET  /admin/api/v1/ops/logs/tail
    SSE endpoint. Streams live log entries from the in-memory ring buffer.
    Supports optional query filters: level, substring, request_id.
"""

import ipaddress
import logging
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse

from ... import backups, db
from ...settings import get_settings
from .. import audit
from ..deps import require_admin
from ..errors import AdminError, to_http
from ..schemas import (
    AdminBackupRow,
    AdminBackupsPage,
    BackupDownloadResponse,
    StartBackupRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/v1/ops", tags=["admin.ops"])


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    try:
        ipaddress.ip_address(request.client.host)
    except ValueError:
        return None
    return request.client.host


# ---------------------------------------------------------------------------
# GET /backups — list backups
# ---------------------------------------------------------------------------


@router.get("/backups", response_model=AdminBackupsPage)
async def list_backups(
    _: Annotated[UUID, Depends(require_admin)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminBackupsPage:
    async with db.as_service_role() as conn:
        from . import service_ops

        return await service_ops.list_backups(conn, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# POST /backups — start a new backup
# ---------------------------------------------------------------------------


@router.post("/backups", response_model=AdminBackupRow, status_code=status.HTTP_202_ACCEPTED)
async def start_backup(
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
    body: StartBackupRequest,
) -> AdminBackupRow:
    async with db.as_service_role() as conn:
        from . import service_ops

        try:
            backup = await service_ops.start_backup(conn, kind=body.kind)
        except AdminError as exc:
            raise to_http(exc) from exc

        ip = _client_ip(request)
        ua = request.headers.get("user-agent")
        await audit.write(
            conn,
            admin_id=admin_id,
            action="backup.start",
            target=str(backup.id),
            payload={"kind": body.kind, "status": backup.status},
            ip=ip,
            ua=ua,
        )
    return backup


# ---------------------------------------------------------------------------
# GET /backups/{id}/download — signed download URL
# ---------------------------------------------------------------------------


@router.get("/backups/{backup_id}/download", response_model=BackupDownloadResponse)
async def get_download_url(
    _: Annotated[UUID, Depends(require_admin)],
    backup_id: UUID,
) -> BackupDownloadResponse:
    async with db.as_service_role() as conn:
        from . import service_ops

        try:
            return await service_ops.get_backup_download_response(conn, backup_id)
        except AdminError as exc:
            raise to_http(exc) from exc


# ---------------------------------------------------------------------------
# GET /downloads/{token} — stream backup file (token-authenticated)
# ---------------------------------------------------------------------------


@router.get("/downloads/{token}")
async def download_backup(request: Request, token: str) -> FileResponse:
    backup_id = backups.verify_download_token(token)
    if backup_id is None:
        raise HTTPException(status_code=403, detail="Invalid or expired download token")

    async with db.as_service_role() as conn:
        record = await backups.get_backup(conn, backup_id)

    if record is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    if record.status != "completed" or not record.file_path:
        raise HTTPException(status_code=409, detail="Backup not ready for download")

    # Defense in depth: refuse to serve any file outside the configured
    # backups directory, even if a stray file_path somehow ends up in the
    # row. The token only authenticates the backup_id, not the path.
    backups_dir = Path(get_settings().backups_dir).resolve()
    target = Path(record.file_path).resolve()
    try:
        target.relative_to(backups_dir)
    except ValueError:
        logger.error(
            "backup %s file_path %s is outside backups_dir %s",
            backup_id,
            target,
            backups_dir,
        )
        raise HTTPException(
            status_code=500, detail="Backup file outside backups directory"
        ) from None

    if not target.is_file():
        logger.error("backup file missing on disk: %s", target)
        raise HTTPException(status_code=500, detail="Backup file missing on disk")

    kind_label = "schema" if record.kind == "schema-only" else "full"
    filename = f"backup_{backup_id}_{kind_label}.sql"

    async with db.as_service_role() as conn:
        await audit.write(
            conn,
            admin_id=None,
            action="backup.download",
            target=str(backup_id),
            payload={"kind": record.kind, "size": record.size},
            ip=_client_ip(request),
            ua=request.headers.get("user-agent"),
        )

    return FileResponse(
        path=str(target),
        media_type="application/sql",
        filename=filename,
    )


# ---------------------------------------------------------------------------
# GET /logs/tail — live log tail via SSE
# ---------------------------------------------------------------------------


@router.get("/logs/tail")
async def tail_logs(
    _: Annotated[UUID, Depends(require_admin)],
    level: Annotated[
        str | None,
        Query(description="Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"),
    ] = None,
    substring: Annotated[
        str | None,
        Query(description="Case-insensitive substring match on message"),
    ] = None,
    request_id: Annotated[
        str | None,
        Query(description="Exact match on request_id field"),
    ] = None,
) -> StreamingResponse:
    from . import service_ops

    return StreamingResponse(
        service_ops.tail_logs(
            level=level,
            substring=substring,
            request_id=request_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
        },
    )
