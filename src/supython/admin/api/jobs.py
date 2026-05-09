"""Admin jobs control plane.

GET  /admin/api/v1/jobs/queue?status=&queue=&limit=&offset=
    Paginated job queue listing with per-status counts.

POST /admin/api/v1/jobs/{id}/retry
    Retry a failed or cancelled job.  Returns 409 unless status is
    retryable.

POST /admin/api/v1/jobs/{id}/cancel
    Cancel a queued job.  Returns 404/409 for non-cancellable states.

GET  /admin/api/v1/jobs/crons
    List cron schedules from ``jobs.cron_schedules`` with pg_cron
    health data.

GET  /admin/api/v1/jobs/crons/health
    pg_cron extension health banner data.

POST /admin/api/v1/jobs/crons/{name}/run-now
    Enqueue the underlying job for a cron schedule once.
"""

import ipaddress
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ... import db
from .. import audit
from ..deps import require_admin
from ..errors import AdminError, to_http
from ..schemas import AdminCronRow, AdminJobRow, AdminJobsPage, PgCronHealth
from . import service_jobs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/v1/jobs", tags=["admin.jobs"])


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    try:
        ipaddress.ip_address(request.client.host)
    except ValueError:
        return None
    return request.client.host


# ---------------------------------------------------------------------------
# GET /queue — paginated job queue
# ---------------------------------------------------------------------------


@router.get("/queue", response_model=AdminJobsPage)
async def list_queue(
    _: Annotated[UUID, Depends(require_admin)],
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    queue: Annotated[str | None, Query(description="Filter by queue name")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminJobsPage:
    async with db.as_service_role() as conn:
        return await service_jobs.list_queue(
            conn,
            status=status,
            queue=queue,
            limit=limit,
            offset=offset,
        )


# ---------------------------------------------------------------------------
# POST /{id}/retry — retry a terminal job
# ---------------------------------------------------------------------------


@router.post("/{job_id}/retry", response_model=AdminJobRow)
async def retry_job(
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
    job_id: UUID,
) -> AdminJobRow:
    async with db.as_service_role() as conn:
        try:
            job = await service_jobs.retry_job(conn, job_id)
        except AdminError as exc:
            raise to_http(exc) from exc

        ip = _client_ip(request)
        ua = request.headers.get("user-agent")
        await audit.write(
            conn,
            admin_id=admin_id,
            action="jobs.retry",
            target=str(job_id),
            payload={"name": job.name, "status": job.status},
            ip=ip,
            ua=ua,
        )
    return job


# ---------------------------------------------------------------------------
# POST /{id}/cancel — cancel a queued job
# ---------------------------------------------------------------------------


@router.post("/{job_id}/cancel", response_model=AdminJobRow)
async def cancel_job(
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
    job_id: UUID,
) -> AdminJobRow:
    async with db.as_service_role() as conn:
        try:
            job = await service_jobs.cancel_job(conn, job_id)
        except AdminError as exc:
            raise to_http(exc) from exc

        ip = _client_ip(request)
        ua = request.headers.get("user-agent")
        await audit.write(
            conn,
            admin_id=admin_id,
            action="jobs.cancel",
            target=str(job_id),
            payload={"name": job.name},
            ip=ip,
            ua=ua,
        )
    return job


# ---------------------------------------------------------------------------
# GET /crons — list cron schedules
# ---------------------------------------------------------------------------


@router.get("/crons", response_model=list[AdminCronRow])
async def list_crons(
    _: Annotated[UUID, Depends(require_admin)],
) -> list[AdminCronRow]:
    async with db.as_service_role() as conn:
        return await service_jobs.list_crons(conn)


# ---------------------------------------------------------------------------
# GET /crons/health — pg_cron health banner
# ---------------------------------------------------------------------------


@router.get("/crons/health", response_model=PgCronHealth)
async def cron_health(
    _: Annotated[UUID, Depends(require_admin)],
) -> PgCronHealth:
    async with db.as_service_role() as conn:
        return await service_jobs.pg_cron_health(conn)


# ---------------------------------------------------------------------------
# POST /crons/{name}/run-now — enqueue a cron's underlying job once
# ---------------------------------------------------------------------------


@router.post("/crons/{cron_name}/run-now", response_model=AdminJobRow)
async def run_cron_now(
    request: Request,
    admin_id: Annotated[UUID, Depends(require_admin)],
    cron_name: str,
) -> AdminJobRow:
    async with db.as_service_role() as conn:
        try:
            job = await service_jobs.run_cron_now(conn, cron_name)
        except AdminError as exc:
            raise to_http(exc) from exc

        ip = _client_ip(request)
        ua = request.headers.get("user-agent")
        await audit.write(
            conn,
            admin_id=admin_id,
            action="jobs.run_cron_now",
            target=cron_name,
            payload={"job_id": str(job.id), "job_name": job.name},
            ip=ip,
            ua=ua,
        )
    return job
